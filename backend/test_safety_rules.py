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

# 2. Battery never goes below the reserve: at 22% of 10 kWh, 0.2 kWh is above the 20%
#    reserve, and discharge losses (efficiency) leave 0.19 kW for the load
out = enforce_safety_node(base_state(battery_soc_pct=22.0, decision=decide(battery=3.0)))
assert out["decision"]["battery_used_kw"] == 0.19, out["decision"]
assert out["decision"]["grid_used_kw"] == 2.81, out["decision"]

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

# 7b. Surplus solar the allocator forgot to store is charged into the battery
out = enforce_safety_node(base_state(solar_kw=6.0, battery_soc_pct=50.0, decision=decide(solar=6.0)))
assert out["decision"]["battery_used_kw"] == -3.0 and out["decision"]["solar_used_kw"] == 3.0, out["decision"]
out = enforce_safety_node(base_state(solar_kw=9.0, battery_soc_pct=50.0, decision=decide(solar=3.0)))
assert out["decision"]["battery_used_kw"] == -5.0, out["decision"]   # 5 kW charge-rate cap

# 7c. Solar left after load and a full battery is exported (net metering)
out = enforce_safety_node(base_state(solar_kw=6.0, battery_soc_pct=100.0, decision=decide(solar=3.0)))
assert out["decision"]["grid_export_kw"] == 3.0 and out["decision"]["battery_used_kw"] == 0.0, out["decision"]
out = enforce_safety_node(base_state(solar_kw=6.0, battery_soc_pct=50.0, decision=decide(solar=3.0)))
assert out["decision"]["grid_export_kw"] == 0.0, out["decision"]   # battery had room, so it charged instead

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

# 9b. The forecast check runs in sensing, before the decision, and belongs to one hour only
import nodes.sensing as sensing
from nodes.sensing import read_and_forecast_node
sensing.fetch_hourly_irradiance = lambda: sensing._simulate_clear_sky_curve()   # offline
fresh = read_and_forecast_node({"sim_hour": 12, "replanned": True, "seed": 7})
assert fresh["replanned"] is False and fresh["forecast_miss_kw"] is None, fresh   # no earlier forecast yet
missed = read_and_forecast_node({"sim_hour": 12, "forecast_solar_kw": 99.0, "seed": 7})
assert missed["replanned"] is True and missed["forecast_miss_kw"] < -1, missed
close = read_and_forecast_node({"sim_hour": 12, "forecast_solar_kw": fresh["solar_kw"], "seed": 7})
assert close["replanned"] is False and close["forecast_miss_kw"] == 0.0, close

# 9c. Same seed + same hour = same clouds and demand; a different seed differs
again = read_and_forecast_node({"sim_hour": 12, "seed": 7})
assert (again["solar_kw"], again["critical_load_kw"]) == (fresh["solar_kw"], fresh["critical_load_kw"])
other = read_and_forecast_node({"sim_hour": 12, "seed": 8})
assert (other["solar_kw"], other["critical_load_kw"]) != (fresh["solar_kw"], fresh["critical_load_kw"])

# 10. Fixed rule (the baseline) through the same safety + apply: solar, then battery to
#     the reserve, then grid; surplus charges, with charge/discharge losses
from nodes.decide import fixed_rule_decision
from nodes.apply import apply_decision_node


def fixed(**overrides):
    state = base_state(**overrides)
    out = enforce_safety_node({**state, "decision": fixed_rule_decision(state)})
    return out, apply_decision_node(out)


night, after = fixed(battery_soc_pct=22.0, flexible_loads=[pump])
assert night["decision"]["battery_used_kw"] == 0.19 and night["decision"]["grid_used_kw"] == 4.31, night["decision"]
assert night["alerts"] == [] and after["battery_soc_pct"] == 20.02, (night["alerts"], after["battery_soc_pct"])
sunny, after = fixed(battery_soc_pct=50.0, solar_kw=6.0)
assert sunny["decision"]["battery_used_kw"] == -3.0 and sunny["decision"]["grid_used_kw"] == 0.0, sunny["decision"]
assert after["battery_soc_pct"] == 78.77, after["battery_soc_pct"]   # 3 kWh in, 95.9% of it stored
full, _ = fixed(battery_soc_pct=100.0, solar_kw=6.0)
assert full["decision"]["grid_export_kw"] == 3.0, full["decision"]
assert generate_report_node({**full, "flexible_loads": []})["report"]["net_cost_rs"] == -9.0

# 10b. Physics: solar losses, heat and inverter clipping; battery efficiency and wear
import physics
assert physics.pv_ac_kw(1000, 25) == 7.22, physics.pv_ac_kw(1000, 25)     # 14% losses, hot cells, inverter
assert physics.pv_ac_kw(1300, -10) == 10.0                                 # never above the 10 kW inverter
assert physics.pv_ac_kw(0, 30) == 0.0
assert round(physics.soc_after(50, 2, 10), 2) == 29.15 and round(physics.soc_after(50, -2, 10), 2) == 69.18
assert physics.wear_cost_rs(-3) == 0.0 and physics.wear_cost_rs(2) > 0

# 12. Power cut: no grid, flexible jobs wait, battery then genset (with its minimum load), then unserved
cut, _ = fixed(grid_available=False, flexible_loads=[pump])
assert cut["decision"]["grid_used_kw"] == 0.0 and cut["decision"]["battery_used_kw"] == 3.0, cut["decision"]
assert cut["decision"]["defer_loads"] == [pump["name"]] and cut["decision"]["genset_kw"] == 0.0, cut["decision"]
low, _ = fixed(grid_available=False, battery_soc_pct=22.0)
assert low["decision"]["genset_kw"] == 2.81 and low["decision"]["battery_used_kw"] == 0.19, low["decision"]
tiny = enforce_safety_node(base_state(grid_available=False, battery_soc_pct=20.5, solar_kw=2.5,
                                      decision=decide(solar=2.5, battery=0.05)))["decision"]
assert tiny["genset_kw"] == 1.5 and tiny["battery_used_kw"] < 0, tiny   # min-load genset covers the gap and charges
short = enforce_safety_node(base_state(grid_available=False, battery_soc_pct=20.0, critical_load_kw=7.0,
                                       decision=decide(grid=7.0)))
assert short["decision"]["genset_kw"] == 5.0 and short["decision"]["unserved_kw"] == 2.0, short["decision"]
assert any("could not be served" in a for a in short["alerts"])
assert short["decision"]["grid_export_kw"] == 0.0

# 13. BMS: limits taper near full/empty, and injected faults isolate the battery
from bms import bms_limits
assert bms_limits(95.0, 1.0)["max_charge_kw"] == 2.5 and bms_limits(50.0, 1.0)["max_charge_kw"] == 5.0
assert bms_limits(22.0, 1.0)["max_discharge_kw"] == 2.0
hot = bms_limits(60.0, 1.0, fault="overtemp")
assert hot["max_discharge_kw"] == 0.0 and hot["alarms"], hot
iso = enforce_safety_node(base_state(bms=hot, decision=decide(battery=3.0)))
assert iso["decision"]["battery_used_kw"] == 0.0 and iso["decision"]["grid_used_kw"] == 3.0, iso["decision"]
assert any(a.startswith("BMS:") for a in iso["alerts"])
assert bms_limits(60.0, 1.0, 50.0)["max_charge_kw"] == 2.5   # 53 degC battery: limits halved

# 11. Export earns credit and counts as avoided CO2 in the report
state = base_state(solar_kw=6.0, decision={**decide(solar=3.0), "grid_export_kw": 3.0})
report = generate_report_node(state)["report"]
assert report["export_credit_rs"] == 9.0 and report["savings_rs"] == 24.0 + 9.0, report
assert report["solar_self_used_kw"] == 3.0, report

print("Safety rules, load carry-over, report, baseline and export checks passed.")
