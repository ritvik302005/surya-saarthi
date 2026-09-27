import physics
from config import (CYCLE_HOURS, GRID_EMISSION_FACTOR_KG_PER_KWH, EXPORT_CREDIT_RS_PER_KWH,
                    GENSET_RS_PER_KWH, GENSET_KWH_PER_L, DIESEL_CO2_KG_PER_L)


def generate_report_node(state):
    decision = state["decision"]
    grid_used = decision.get("grid_used_kw", 0)
    price = state["grid_price_per_kwh"]
    grid_ok = state.get("grid_available", True)

    # Baseline: a site with no solar or battery serving the same loads this hour — from
    # the grid, or from a diesel genset in a power cut (what such sites use today). Every
    # flexible job is served exactly once (deferred jobs carry forward), so over a full
    # run this counts all demand without double counting.
    deferred = [l["name"] for l in state["flexible_loads"] if l.get("deferred")]
    served_load_kw = round(state["critical_load_kw"] + sum(
        l["power_kw"] for l in state["flexible_loads"] if not l.get("deferred")
    ) - decision.get("unserved_kw", 0), 2)

    baseline_cost = round(served_load_kw * (price if grid_ok else GENSET_RS_PER_KWH) * CYCLE_HOURS, 2)
    import_cost = round(grid_used * price * CYCLE_HOURS, 2)
    export_kw = decision.get("grid_export_kw", 0)
    export_credit = round(export_kw * EXPORT_CREDIT_RS_PER_KWH * CYCLE_HOURS, 2)
    battery_kw = decision.get("battery_used_kw", 0)
    wear_cost = round(physics.wear_cost_rs(battery_kw), 2)
    genset_kw = decision.get("genset_kw", 0)
    diesel_l = physics.genset_fuel_l(genset_kw)
    fuel_cost = round(genset_kw * GENSET_RS_PER_KWH * CYCLE_HOURS, 2)
    net_cost = round(import_cost - export_credit + wear_cost + fuel_cost, 2)
    savings = round(baseline_cost - net_cost, 2)

    # Exported solar displaces grid generation elsewhere, so it also avoids CO2; diesel adds CO2.
    baseline_factor = GRID_EMISSION_FACTOR_KG_PER_KWH if grid_ok else DIESEL_CO2_KG_PER_L / GENSET_KWH_PER_L
    baseline_carbon = round(served_load_kw * CYCLE_HOURS * baseline_factor, 2)
    actual_carbon = round((grid_used - export_kw) * CYCLE_HOURS * GRID_EMISSION_FACTOR_KG_PER_KWH
                          + diesel_l * DIESEL_CO2_KG_PER_L, 2)
    carbon_avoided = round(baseline_carbon - actual_carbon, 2)

    solar_available = state.get("solar_kw", 0)
    # Charging draws on surplus solar first (any rest comes from genset excess).
    solar_to_battery = min(max(0.0, -battery_kw), max(0.0, solar_available - decision.get("solar_used_kw", 0)))
    solar_self_used = decision.get("solar_used_kw", 0) + solar_to_battery

    report = {
        "grid_used_kw": grid_used,
        "served_load_kw": served_load_kw,
        "cost_rs": import_cost,
        "baseline_cost_rs": baseline_cost,
        "export_kw": export_kw,
        "export_credit_rs": export_credit,
        "battery_wear_rs": wear_cost,
        "genset_kw": genset_kw,
        "diesel_l": round(diesel_l, 3),
        "fuel_cost_rs": fuel_cost,
        "unserved_kw": decision.get("unserved_kw", 0),
        "grid_available": grid_ok,
        "net_cost_rs": net_cost,          # import - export credit + battery wear + diesel
        "solar_available_kw": solar_available,
        "solar_self_used_kw": round(solar_self_used, 2),
        "solar_curtailed_kw": decision.get("solar_curtailed_kw", 0),
        "savings_rs": savings,
        "carbon_avoided_kg": carbon_avoided,
        "deferred_loads": deferred,
        "alerts": state["alerts"],
        "replanned_this_cycle": state.get("replanned", False),   # forecast missed, so planned cautiously
        "forecast_miss_kw": state.get("forecast_miss_kw"),
    }

    out = {**state, "report": report}
    facts = state.get("explain_facts")
    if facts:
        # Optimizer explanations: describe what was actually applied after the safety check.
        from explain import explain
        charge = max(0.0, -battery_kw)
        applied = {**facts, "charge_kw": charge, "discharge_kw": max(0.0, battery_kw), "grid_kw": grid_used,
                   "genset_kw": genset_kw, "export_kw": export_kw}
        out["reasoning"], out["reasoning_hi"] = explain(applied)
        out["explain_facts"] = None
    return out
