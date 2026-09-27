import physics


def apply_decision_node(state):
    """Applies the (safety-checked) decision to the battery and the flexible jobs.
    Runs exactly once per simulated hour: the forecast check happens in sensing,
    before the decision, so nothing loops back through here."""
    decision = state["decision"]
    battery_used_kw = decision.get("battery_used_kw", 0)

    # Positive battery_used_kw is discharge delivered to the site; negative is charging.
    # Charging and discharging both lose energy (round-trip efficiency), and energy taken
    # out wears the battery (state of health).
    new_soc = physics.soc_after(state["battery_soc_pct"], battery_used_kw, state["battery_capacity_kwh"])
    new_soh = physics.soh_after(state.get("battery_soh", 1.0), battery_used_kw)

    defer_names = set(decision.get("defer_loads", []))
    updated_loads = [
        {**load, "deferred": load["name"] in defer_names}
        for load in state["flexible_loads"]
    ]

    return {
        **state,
        "battery_soc_pct": round(new_soc, 2),
        "battery_soh": new_soh,
        "flexible_loads": updated_loads,
    }
