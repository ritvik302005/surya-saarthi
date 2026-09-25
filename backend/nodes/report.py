from config import CYCLE_HOURS, GRID_EMISSION_FACTOR_KG_PER_KWH

def generate_report_node(state):
    decision = state["decision"]
    grid_used = decision.get("grid_used_kw", 0)
    critical = state["critical_load_kw"]
    price = state["grid_price_per_kwh"]

    baseline_cost = round(critical * price * CYCLE_HOURS, 2)
    actual_cost = round(grid_used * price * CYCLE_HOURS, 2)
    savings = round(baseline_cost - actual_cost, 2)

    baseline_carbon = round(critical * CYCLE_HOURS * GRID_EMISSION_FACTOR_KG_PER_KWH, 2)
    actual_carbon = round(grid_used * CYCLE_HOURS * GRID_EMISSION_FACTOR_KG_PER_KWH, 2)
    carbon_avoided = round(baseline_carbon - actual_carbon, 2)

    report = {
        "grid_used_kw": grid_used,
        "cost_rs": actual_cost,
        "savings_rs": savings,
        "carbon_avoided_kg": carbon_avoided,
        "deferred_loads": [l["name"] for l in state["flexible_loads"] if l.get("deferred")],
        "alerts": state["alerts"],
        "replanned_this_cycle": state.get("replanned", False)
    }

    return {**state, "report": report}