from config import CYCLE_HOURS, BATTERY_RESERVE_PCT, BATTERY_MAX_CHARGE_KW, BATTERY_MAX_DISCHARGE_KW

TOLERANCE_KW = 0.01  # ignore rounding-level differences so overrides only fire on real violations

def enforce_safety_node(state):
    decision = dict(state["decision"])  # copy so we don't mutate the LLM's original response
    alerts = list(state.get("alerts", []))

    solar_used = max(0, decision.get("solar_used_kw", 0))
    battery_used = decision.get("battery_used_kw", 0)
    grid_used = max(0, decision.get("grid_used_kw", 0))
    solar_available = max(0, state.get("solar_kw", 0))

    # --- Check 0: jobs at their deadline can't be deferred again ---
    must_run = {load["name"] for load in state.get("flexible_loads", []) if load.get("must_run")}
    defer_loads = list(decision.get("defer_loads", []))
    forced = [name for name in defer_loads if name in must_run]
    if forced:
        defer_loads = [name for name in defer_loads if name not in must_run]
        alerts.append(f"Safety override: {', '.join(forced)} reached its deadline and cannot be deferred again.")

    # --- Check 1: can't use more solar than is actually being generated ---
    if solar_used > solar_available + TOLERANCE_KW:
        shortfall = round(solar_used - solar_available, 2)
        solar_used = solar_available
        grid_used += shortfall
        alerts.append(f"Safety override: allocator used {shortfall} kW more solar than was generated ({solar_available} kW), shifted to grid.")

    if battery_used >= 0:
        # --- Check 2: discharge — reserve floor AND an absolute rate ceiling ---
        available_kwh = max(0, (state["battery_soc_pct"] - BATTERY_RESERVE_PCT) / 100 * state["battery_capacity_kwh"])
        max_battery_kw = min(available_kwh / CYCLE_HOURS, BATTERY_MAX_DISCHARGE_KW)

        if battery_used > max_battery_kw + TOLERANCE_KW:
            shortfall = round(battery_used - max_battery_kw, 2)
            battery_used = round(max_battery_kw, 2)
            grid_used += shortfall
            alerts.append(f"Safety override: capped battery discharge to protect {BATTERY_RESERVE_PCT}% reserve / {BATTERY_MAX_DISCHARGE_KW} kW rate limit, shifted {shortfall} kW to grid.")
    else:
        # --- Check 2B: charging — only from surplus solar, can't pass 100% SOC or the charge-rate limit ---
        charge_kw = -battery_used
        room_kwh = max(0, (100.0 - state["battery_soc_pct"]) / 100 * state["battery_capacity_kwh"])
        surplus_solar = max(0, solar_available - solar_used)
        max_charge_kw = min(room_kwh / CYCLE_HOURS, BATTERY_MAX_CHARGE_KW, surplus_solar)

        if charge_kw > max_charge_kw + TOLERANCE_KW:
            capped = round(charge_kw - max_charge_kw, 2)
            battery_used = round(-max_charge_kw, 2)
            alerts.append(f"Safety override: capped battery charging at {max_charge_kw:.2f} kW (surplus solar, 100% SOC or {BATTERY_MAX_CHARGE_KW} kW rate limit), {capped} kW not charged.")

    # --- Check 3: every load that isn't deferred must actually be powered ---
    # (charging doesn't serve load, so a negative battery_used contributes 0)
    demand_kw = state["critical_load_kw"] + sum(
        load["power_kw"] for load in state.get("flexible_loads", []) if load["name"] not in defer_loads
    )
    supplied = solar_used + max(0, battery_used) + grid_used
    if supplied < demand_kw - TOLERANCE_KW:
        shortfall = round(demand_kw - supplied, 2)
        grid_used = round(grid_used + shortfall, 2)
        alerts.append(f"Safety override: {shortfall} kW of demand was left unpowered by the allocator, forced from grid.")
    elif supplied > demand_kw and grid_used > 0:
        # don't buy grid power nothing is using
        grid_used = max(0, grid_used - (supplied - demand_kw))

    # --- Check 4: surplus solar is never wasted while the battery has room ---
    # solar_used_kw means solar serving load; solar going into the battery is
    # represented only by a negative battery_used_kw (same as the prompt says).
    if battery_used <= 0:
        solar_for_load = min(solar_used, max(0, demand_kw - grid_used))
        charge_kw = -battery_used
        leftover = max(0, solar_available - solar_for_load - charge_kw)
        room_kw = max(0, (100.0 - state["battery_soc_pct"]) / 100 * state["battery_capacity_kwh"]) / CYCLE_HOURS
        extra = min(leftover, max(0, room_kw - charge_kw), max(0, BATTERY_MAX_CHARGE_KW - charge_kw))
        battery_used = -(charge_kw + extra)
        solar_used = solar_for_load

    decision["solar_used_kw"] = round(solar_used, 2)
    decision["battery_used_kw"] = round(battery_used, 2)
    decision["grid_used_kw"] = round(grid_used, 2)
    decision["defer_loads"] = defer_loads

    return {
        **state,
        "decision": decision,
        "alerts": alerts
    }
