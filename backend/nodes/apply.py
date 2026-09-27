from config import CYCLE_HOURS


def apply_decision_node(state):
    """Applies the (safety-checked) decision to the battery and the flexible jobs.
    Runs exactly once per simulated hour: the forecast check now happens in
    sensing, before the decision, so nothing loops back through here."""
    decision = state["decision"]
    battery_used_kw = decision.get("battery_used_kw", 0)

    # Positive battery_used_kw is discharge (SOC falls), negative is charging (SOC rises).
    # safety.py already keeps the request inside 0-100%; clamping here keeps this
    # function correct on its own.
    pct_change = (battery_used_kw * CYCLE_HOURS / state["battery_capacity_kwh"]) * 100
    new_soc = min(100, max(0, state["battery_soc_pct"] - pct_change))

    defer_names = set(decision.get("defer_loads", []))
    updated_loads = [
        {**load, "deferred": load["name"] in defer_names}
        for load in state["flexible_loads"]
    ]

    return {
        **state,
        "battery_soc_pct": round(new_soc, 2),
        "flexible_loads": updated_loads,
    }
