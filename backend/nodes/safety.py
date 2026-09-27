"""Hard safety rules and plant physics, applied to EVERY controller's proposal
(the AI, the optimizer and the fixed rule), so all are judged on the same terms.

Order: jobs -> solar serves load -> battery (within BMS and reserve limits) -> genset
-> grid (or, in a power cut: more battery -> genset -> unserved) -> surplus charges
the battery -> leftover solar is exported (or curtailed in a power cut). Grid import
above a demand-response limit is reported, not forced down.
"""
import physics
from bms import bms_limits
from config import (GENSET_KW, GENSET_MIN_LOAD_FRACTION, GRID_EXPORT_LIMIT_KW)
from nodes.sensing import dr_cap_kw

TOLERANCE_KW = 0.01  # ignore rounding-level differences so overrides only fire on real violations


def _genset_output(requested_kw):
    """A running genset delivers at least its minimum load and at most its rating."""
    if requested_kw <= TOLERANCE_KW:
        return 0.0
    return min(GENSET_KW, max(requested_kw, GENSET_KW * GENSET_MIN_LOAD_FRACTION))


def enforce_safety_node(state):
    proposal = dict(state["decision"])  # keep the controller's original proposal untouched
    decision = dict(proposal)
    alerts = list(state.get("alerts", []))

    soc = state["battery_soc_pct"]
    capacity = state["battery_capacity_kwh"]
    bms = state.get("bms") or bms_limits(soc, state.get("battery_soh", 1.0))
    grid_ok = state.get("grid_available", True)
    solar_available = max(0.0, state.get("solar_kw", 0))
    loads = state.get("flexible_loads", [])

    # --- Check 0: jobs. At their deadline they can't be deferred; in a power cut the
    # other flexible jobs wait, so only essentials run on battery/genset. ---
    must_run = {load["name"] for load in loads if load.get("must_run")}
    known = {load["name"] for load in loads}
    defer_loads = [name for name in proposal.get("defer_loads", []) if name in known]
    forced = [name for name in defer_loads if name in must_run]
    if forced:
        defer_loads = [name for name in defer_loads if name not in must_run]
        alerts.append(f"Safety override: {', '.join(forced)} reached its deadline and cannot be deferred again.")
    if not grid_ok:
        waiting = [load["name"] for load in loads if load["name"] not in must_run and load["name"] not in defer_loads]
        if waiting:
            defer_loads += waiting
            alerts.append(f"Power cut: {', '.join(waiting)} will wait; essentials only on battery and genset.")

    demand = state["critical_load_kw"] + sum(load["power_kw"] for load in loads if load["name"] not in defer_loads)

    # --- Check 1: can't use more solar than is generated; solar always serves load first ---
    proposed_solar = max(0.0, proposal.get("solar_used_kw", 0))
    if proposed_solar > solar_available + TOLERANCE_KW:
        alerts.append(f"Safety override: allocator used {round(proposed_solar - solar_available, 2)} kW more solar "
                      f"than was generated ({solar_available} kW), shifted to other sources.")
    solar_to_load = min(solar_available, demand)
    remaining = demand - solar_to_load

    # --- Check 2: battery within the reserve and the BMS's live limits ---
    max_dis = min(physics.max_discharge_kw(soc, capacity), bms["max_discharge_kw"])
    max_chg = min(physics.max_charge_kw(soc, capacity), bms["max_charge_kw"])
    battery = proposal.get("battery_used_kw", 0)
    if battery > max_dis + TOLERANCE_KW:
        alerts.append(f"Safety override: capped battery discharge at {max_dis:.2f} kW (reserve, rate limit or BMS), "
                      f"shifted {round(battery - max_dis, 2)} kW to other sources.")
        battery = max_dis
    battery_out = min(max(0.0, battery), remaining)   # never discharge more than the load needs
    remaining -= battery_out

    # --- Check 3: genset (if the controller asked for it) serves load next ---
    genset = _genset_output(max(0.0, proposal.get("genset_kw", 0)))
    genset_to_load = min(genset, remaining)
    remaining -= genset_to_load

    # --- Check 4: the rest comes from the grid, or in a power cut from battery -> genset -> unserved ---
    grid_used, unserved = 0.0, 0.0
    if grid_ok:
        grid_used = remaining
        if remaining > max(0.0, proposal.get("grid_used_kw", 0)) + TOLERANCE_KW:
            alerts.append(f"Safety override: {round(remaining - max(0.0, proposal.get('grid_used_kw', 0)), 2)} kW "
                          f"of demand was left unpowered by the allocator, forced from grid.")
        remaining = 0.0
    else:
        if remaining > TOLERANCE_KW:
            extra = min(remaining, max(0.0, max_dis - battery_out))
            battery_out += extra
            remaining -= extra
        if remaining > TOLERANCE_KW:
            before = genset
            genset = _genset_output(genset_to_load + remaining) if genset < GENSET_KW else genset
            added = min(genset - genset_to_load, remaining)
            genset_to_load += added
            remaining -= added
            if genset > before:
                alerts.append(f"Power cut: genset running at {genset:.1f} kW for essential load.")
        if remaining > TOLERANCE_KW:
            unserved = remaining
            alerts.append(f"Power cut: {unserved:.2f} kW of essential load could not be served.")
        remaining = 0.0
    # A running genset's spare output (it can't go below its minimum load) serves the load
    # before the battery does, so the battery isn't drained while diesel is wasted.
    spare = genset - genset_to_load
    if spare > TOLERANCE_KW and battery_out > 0:
        shift = min(spare, battery_out)
        battery_out -= shift
        genset_to_load += shift

    # --- Check 5: surplus (solar, then any extra genset output) charges the battery; never the grid ---
    surplus_solar = solar_available - solar_to_load
    genset_excess = genset - genset_to_load
    charge = 0.0
    if battery_out <= TOLERANCE_KW:
        battery_out = 0.0
        wanted = max(0.0, -battery) if battery < 0 else 0.0
        charge = min(max_chg, surplus_solar + genset_excess)
        if wanted > charge + TOLERANCE_KW:
            alerts.append(f"Safety override: capped battery charging at {charge:.2f} kW (surplus power, 100% SOC, "
                          f"rate limit or BMS), {round(wanted - charge, 2)} kW not charged.")
    solar_to_battery = min(charge, surplus_solar)
    genset_wasted = genset_excess - (charge - solar_to_battery)

    # --- Check 6: leftover solar is exported (net metering), or curtailed in a power cut ---
    solar_left = surplus_solar - solar_to_battery
    export = min(solar_left, GRID_EXPORT_LIMIT_KW) if grid_ok else 0.0

    # --- Check 7: demand response. A DISCOM grid-import limit is a request, not a physical
    # limit, so it is not forced (essentials stay powered); going over it is reported. ---
    cap = dr_cap_kw(state.get("dr_events"), state.get("sim_hour", 0))
    if cap is not None and grid_used > cap + TOLERANCE_KW:
        alerts.append(f"Demand response: grid import {grid_used:.2f} kW is above the {cap:.1f} kW limit "
                      f"asked for this hour.")

    battery_used = battery_out if battery_out > 0 else -charge
    decision.update({
        "solar_used_kw": round(solar_to_load, 2),
        "battery_used_kw": round(battery_used, 2) if abs(battery_used) >= 0.005 else 0.0,   # avoid -0.0
        "grid_used_kw": round(grid_used, 2),
        "genset_kw": round(genset, 2),
        "genset_wasted_kw": round(max(0.0, genset_wasted), 2),
        "grid_export_kw": round(export, 2),
        "solar_curtailed_kw": round(solar_left - export, 2),
        "unserved_kw": round(unserved, 2),
        "defer_loads": defer_loads,
    })
    alerts += [f"BMS: {a}" for a in bms.get("alarms", []) if f"BMS: {a}" not in alerts]
    return {**state, "decision": decision, "alerts": alerts}
