"""Fast, offline checks for the hard safety rules, load carry-over and report.

Run from backend with: python test_safety_rules.py
"""

from nodes.safety import enforce_safety_node
from nodes.sensing import merge_flexible_loads
from nodes.report import generate_report_node


def base_state(**overrides):
    state = {
        "solar_kw": 0.0,
        "battery_soc_pct": 60.0,
        "battery_capacity_kwh": 10.0,
        "critical_load_kw": 3.0,
        "flexible_loads": [],
        "grid_price_per_kwh": 8.0,
        "alerts": [],
    }
    state.update(overrides)
    return state


def decide(solar=0.0, battery=0.0, grid=0.0, defer=()):
    return {"solar_used_kw": solar, "battery_used_kw": battery, "grid_used_kw": grid,
            "defer_loads": list(defer), "reasoning": "test"}


# 1. Phantom solar at night is capped and moved to grid
out = enforce_safety_node(base_state(decision=decide(solar=3.0)))
assert out["decision"]["solar_used_kw"] == 0.0, out["decision"]
assert out["decision"]["grid_used_kw"] == 3.0, out["decision"]
assert any("more solar than was generated" in a for a in out["alerts"])

# 2. Battery never goes below the reserve (60% of 10 kWh -> 4 kWh usable, 5 kW rate cap)
out = enforce_safety_node(base_state(battery_soc_pct=22.0, decision=decide(battery=3.0)))
assert out["decision"]["battery_used_kw"] == 0.2, out["decision"]
assert out["decision"]["grid_used_kw"] == 2.8, out["decision"]

# 3. A non-deferred flexible load left unpowered is topped up from grid
pump = {"name": "water_pump (07:00)", "power_kw": 1.5, "deadline_hour": 10, "deferred": False}
out = enforce_safety_node(base_state(flexible_loads=[pump], decision=decide(grid=3.0)))
assert out["decision"]["grid_used_kw"] == 4.5, out["decision"]

# 4. Deferring it is fine: no top-up
out = enforce_safety_node(base_state(flexible_loads=[pump], decision=decide(grid=3.0, defer=[pump["name"]])))
assert out["decision"]["grid_used_kw"] == 3.0, out["decision"]
assert out["alerts"] == [], out["alerts"]

# 5. A must_run job can't be deferred; it is powered from grid instead
due = {**pump, "must_run": True}
out = enforce_safety_node(base_state(flexible_loads=[due], decision=decide(grid=3.0, defer=[due["name"]])))
assert out["decision"]["defer_loads"] == [], out["decision"]
assert out["decision"]["grid_used_kw"] == 4.5, out["decision"]

# 6. Charging only from surplus solar, never from grid
out = enforce_safety_node(base_state(solar_kw=4.0, decision=decide(solar=3.0, battery=-4.0)))
assert out["decision"]["battery_used_kw"] == -1.0, out["decision"]

# 7. Extra grid nobody uses is not bought
out = enforce_safety_node(base_state(solar_kw=3.0, decision=decide(solar=3.0, grid=2.0)))
assert out["decision"]["grid_used_kw"] == 0.0, out["decision"]

# 8. Deferred jobs carry forward and become must_run in their last hour
ev = {"name": "ev_charging (22:00)", "power_kw": 3.0, "deadline_hour": 6, "deferred": True}
ran = {**pump, "deferred": False}
assert [l["name"] for l in merge_flexible_loads([ev, ran], [], 23)] == [ev["name"]]
assert merge_flexible_loads([ev], [], 23)[0]["must_run"] is False
assert merge_flexible_loads([ev], [], 5)[0]["must_run"] is True

# 9. Savings baseline counts served flexible loads, not deferred ones
state = base_state(flexible_loads=[{**pump, "deferred": False}, {**ev, "deferred": True}],
                   decision=decide(grid=1.5))
report = generate_report_node(state)["report"]
assert report["served_load_kw"] == 4.5, report
assert report["savings_rs"] == round((4.5 - 1.5) * 8.0, 2), report
assert report["deferred_loads"] == [ev["name"]], report

print("Safety rules, load carry-over and report checks passed.")
