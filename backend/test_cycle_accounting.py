"""Offline, whole-pipeline energy accounting checks (no Groq, no network).

Runs 48 simulated hours through the real graph for each controller (the AI with a
stub LLM, the optimizer, the fixed rule), with and without a power cut, and checks
every hour: the battery moves exactly once, by exactly what the final decision says
(with charge/discharge losses); every non-deferred load is powered or counted as
unserved; the grid is never used in a cut; rate limits hold; solar is fully
accounted for. Also: AI off == fixed-rule baseline, and the optimizer's plans pass
the safety check without overrides.

Run from backend with: python test_cycle_accounting.py
"""
import json
from types import SimpleNamespace

import config
import main
import nodes.allocation as allocation
import nodes.sensing as sensing
import physics

TOL = 0.05

# The stub always proposes a 3 kW discharge and no solar/grid, so the safety
# layer has real work to do every hour and night/day both get exercised.
STUB = {"solar_used_kw": 0.0, "battery_used_kw": 3.0, "grid_used_kw": 0.0, "defer_loads": [], "reasoning": "stub"}
allocation._invoke_with_retry = lambda messages: SimpleNamespace(content=json.dumps(STUB))
sensing.download_weather = lambda: (sensing._simulate_clear_sky_curve(), None)
config.AI_HOURS_PER_DAY = config.AI_HOURS_PER_SESSION_PER_DAY = None


def check_run(controller, outages):
    session = main.Session("cloudy", controller=controller)
    session.reset("cloudy", seed=3)   # high variability + fixed seed -> the same forecast misses every run
    session.outages = outages
    soc_before, missed = config.INITIAL_BATTERY_SOC_PCT, 0
    for _ in range(48):
        entry = main._run_one_cycle(session)
        state = session.state
        d = state["decision"]
        hour = entry["sim_hour"]
        missed += entry["replanned"]
        label = f"{controller}, hour {hour}"

        expected = physics.soc_after(soc_before, d["battery_used_kw"], state["battery_capacity_kwh"])
        assert abs(entry["battery_soc_pct"] - expected) < TOL, (
            f"{label}: battery went {soc_before}% -> {entry['battery_soc_pct']}% but the decision "
            f"({d['battery_used_kw']} kW) accounts for {expected:.2f}%")

        # Power reaching the load (genset output that went into the battery or was wasted doesn't count)
        charge_from_genset = max(0, -d["battery_used_kw"]) - min(max(0, -d["battery_used_kw"]), state["solar_kw"] - d["solar_used_kw"])
        to_load = (d["solar_used_kw"] + max(0, d["battery_used_kw"]) + d["grid_used_kw"]
                   + d["genset_kw"] - d.get("genset_wasted_kw", 0) - charge_from_genset)
        assert to_load >= entry["load_kw"] - TOL, f"{label}: {to_load} kW reached a {entry['load_kw']} kW served load"
        if not state["grid_available"]:
            assert d["grid_used_kw"] == 0 and d["grid_export_kw"] == 0, f"{label}: grid used in a power cut"

        assert -config.BATTERY_MAX_CHARGE_KW - TOL <= d["battery_used_kw"] <= config.BATTERY_MAX_DISCHARGE_KW + TOL, (
            f"{label}: battery {d['battery_used_kw']} kW breaks the rate limit")
        assert entry["battery_soc_pct"] >= min(config.BATTERY_RESERVE_PCT, soc_before) - TOL, (
            f"{label}: battery fell below the reserve to {entry['battery_soc_pct']}%")

        solar_to_battery = min(max(0, -d["battery_used_kw"]), state["solar_kw"] - d["solar_used_kw"])
        solar_out = d["solar_used_kw"] + solar_to_battery + d["grid_export_kw"] + d["solar_curtailed_kw"]
        assert abs(solar_out - state["solar_kw"]) < TOL, f"{label}: solar in {state['solar_kw']} vs accounted {solar_out}"

        if controller == "optimizer":
            overrides = [a for a in entry["alerts"] if a.startswith("Safety override")]
            assert not overrides, f"{label}: optimizer plan was overridden: {overrides}"
            h = state["plan"]["hourly"]
            planned = h["d"][0] - h["sc"][0] - h["gc"][0]
            assert abs(planned - d["battery_used_kw"]) < 0.1, (
                f"{label}: plant applied {d['battery_used_kw']} kW, optimizer planned {planned:.2f} kW")
        soc_before = entry["battery_soc_pct"]
    return session, missed


for controller in ("ai", "optimizer", "fixed"):
    for outages in ([], [[19, 22], [43, 46]]):
        session, missed = check_run(controller, outages)
        assert missed > 0, "no forecast miss happened, so the forecast-miss path wasn't exercised"
        c = session.state["comparison"]
        if outages:
            assert c["power_cut_hours"] == 6, c
        if controller == "optimizer" and outages:
            # With the cut known in advance, the optimizer meets it with more battery than the fixed rule.
            cut_soc = [e for e in session.history if e["sim_hour"] == 19][0]
            assert cut_soc["battery_soc_pct"] >= cut_soc["rule_battery_soc_pct"], cut_soc

# Parity: with the AI off, every hour is decided by the fixed rule, which is the same
# logic as the rule-based baseline. Both controllers must then come out identical, so
# in a real run any difference between them is the AI's effect alone.
main._ai_blocked_reason = lambda _session: "test: AI switched off"
for scenario in config.WEATHER_SCENARIOS:
    parity = main.Session(scenario, controller="ai")
    parity.reset(scenario, seed=11)
    parity.outages = [[20, 23]]
    for _ in range(48):
        main._run_one_cycle(parity)
    c = parity.state["comparison"]
    assert c["ai_fallback_hours"] == 48, c
    assert abs(c["agent_grid_kwh"] - c["rule_grid_kwh"]) < TOL and abs(c["agent_cost_rs"] - c["rule_cost_rs"]) < TOL, (
        f"{scenario}: fixed-rule agent and rule-based baseline differ: {c}")

print("Cycle accounting checks passed (3 controllers x with/without power cuts, 48 h each; "
      f"AI-off runs match the rule-based baseline in all {len(config.WEATHER_SCENARIOS)} scenarios).")
