from config import CYCLE_HOURS, GRID_EMISSION_FACTOR_KG_PER_KWH, EXPORT_CREDIT_RS_PER_KWH

def generate_report_node(state):
    decision = state["decision"]
    grid_used = decision.get("grid_used_kw", 0)
    price = state["grid_price_per_kwh"]

    # Baseline: a grid-only site serving the same loads this hour. Every
    # flexible job is served exactly once (deferred jobs carry forward), so
    # over a full run this counts all demand without double counting.
    deferred = [l["name"] for l in state["flexible_loads"] if l.get("deferred")]
    served_load_kw = round(state["critical_load_kw"] + sum(
        l["power_kw"] for l in state["flexible_loads"] if not l.get("deferred")
    ), 2)

    baseline_cost = round(served_load_kw * price * CYCLE_HOURS, 2)
    actual_cost = round(grid_used * price * CYCLE_HOURS, 2)
    export_kw = decision.get("grid_export_kw", 0)
    export_credit = round(export_kw * EXPORT_CREDIT_RS_PER_KWH * CYCLE_HOURS, 2)
    savings = round(baseline_cost - actual_cost + export_credit, 2)

    # Exported solar displaces grid generation elsewhere, so it also avoids CO2.
    baseline_carbon = round(served_load_kw * CYCLE_HOURS * GRID_EMISSION_FACTOR_KG_PER_KWH, 2)
    actual_carbon = round((grid_used - export_kw) * CYCLE_HOURS * GRID_EMISSION_FACTOR_KG_PER_KWH, 2)
    carbon_avoided = round(baseline_carbon - actual_carbon, 2)

    solar_available = state.get("solar_kw", 0)
    solar_self_used = decision.get("solar_used_kw", 0) + max(0, -decision.get("battery_used_kw", 0))

    report = {
        "grid_used_kw": grid_used,
        "served_load_kw": served_load_kw,
        "cost_rs": actual_cost,
        "baseline_cost_rs": baseline_cost,
        "export_kw": export_kw,
        "export_credit_rs": export_credit,
        "net_cost_rs": round(actual_cost - export_credit, 2),
        "solar_available_kw": solar_available,
        "solar_self_used_kw": round(solar_self_used, 2),
        "solar_curtailed_kw": decision.get("solar_curtailed_kw", 0),
        "savings_rs": savings,
        "carbon_avoided_kg": carbon_avoided,
        "deferred_loads": deferred,
        "alerts": state["alerts"],
        "replanned_this_cycle": state.get("replanned", False)
    }

    return {**state, "report": report}
