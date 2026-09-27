"""Offline, whole-pipeline energy accounting checks (no Groq, no network).

Runs 48 simulated hours through the real graph with the LLM replaced by a stub
and the weather fetch replaced by the clear-sky curve, then checks every hour:
the battery level moves exactly once, by exactly what the final decision says;
every non-deferred load is powered; the rate limits hold; and solar is fully
accounted for.

Run from backend with: python test_cycle_accounting.py
"""
import json
from types import SimpleNamespace

import config
import main
import nodes.allocation as allocation
import nodes.sensing as sensing

TOL = 0.05

# The stub always proposes a 3 kW discharge and no solar/grid, so the safety
# layer has real work to do every hour and night/day both get exercised.
STUB = {"solar_used_kw": 0.0, "battery_used_kw": 3.0, "grid_used_kw": 0.0, "defer_loads": [], "reasoning": "stub"}
allocation._invoke_with_retry = lambda messages: SimpleNamespace(content=json.dumps(STUB))
sensing.fetch_hourly_irradiance = lambda: sensing._simulate_clear_sky_curve()
config.AI_HOURS_PER_DAY = config.AI_HOURS_PER_SESSION_PER_DAY = None   # every hour goes through the (stub) AI

session = main.Session("cloudy")
session.reset("cloudy", seed=3)   # high variability + fixed seed -> the same forecast misses every run
soc_before = config.INITIAL_BATTERY_SOC_PCT
replanned_hours = 0

for _ in range(48):
    entry = main._run_one_cycle(session)
    state = session.state
    d = state["decision"]
    hour = entry["sim_hour"]
    replanned_hours += entry["replanned"]

    expected_soc = min(100, max(0, soc_before - d["battery_used_kw"] * config.CYCLE_HOURS / state["battery_capacity_kwh"] * 100))
    assert abs(entry["battery_soc_pct"] - expected_soc) < TOL, (
        f"hour {hour}: battery went {soc_before}% -> {entry['battery_soc_pct']}% but the decision "
        f"({d['battery_used_kw']} kW) accounts for {expected_soc:.2f}% (replanned={entry['replanned']})")

    supplied = d["solar_used_kw"] + max(0, d["battery_used_kw"]) + d["grid_used_kw"]
    assert supplied >= entry["load_kw"] - TOL, f"hour {hour}: {supplied} kW supplied for {entry['load_kw']} kW load"

    assert -config.BATTERY_MAX_CHARGE_KW - TOL <= d["battery_used_kw"] <= config.BATTERY_MAX_DISCHARGE_KW + TOL, (
        f"hour {hour}: battery {d['battery_used_kw']} kW breaks the rate limit")
    assert entry["battery_soc_pct"] >= min(config.BATTERY_RESERVE_PCT, soc_before) - TOL, (
        f"hour {hour}: battery fell below the reserve to {entry['battery_soc_pct']}%")

    solar_out = d["solar_used_kw"] + max(0, -d["battery_used_kw"]) + d["grid_export_kw"] + d["solar_curtailed_kw"]
    assert abs(solar_out - state["solar_kw"]) < TOL, f"hour {hour}: solar in {state['solar_kw']} vs accounted {solar_out}"

    soc_before = entry["battery_soc_pct"]

assert replanned_hours > 0, "no forecast miss happened, so the forecast-miss path wasn't exercised"

# Parity: with the AI off, every hour is decided by the fixed rule, which is the same
# logic as the rule-based baseline. Both controllers must then come out identical, so
# in a real run any difference between them is the AI's effect alone.
main._ai_blocked_reason = lambda _session: "test: AI switched off"
for scenario in config.WEATHER_SCENARIOS:
    parity = main.Session(scenario)
    parity.reset(scenario, seed=11)
    for _ in range(48):
        main._run_one_cycle(parity)
    c = parity.state["comparison"]
    assert c["ai_fallback_hours"] == 48, c
    assert abs(c["agent_grid_kwh"] - c["rule_grid_kwh"]) < TOL and abs(c["agent_cost_rs"] - c["rule_cost_rs"]) < TOL, (
        f"{scenario}: fixed-rule agent and rule-based baseline differ: {c}")

print(f"Cycle accounting checks passed (48 hours, {replanned_hours} with a forecast miss; "
      f"AI-off runs match the rule-based baseline in all {len(config.WEATHER_SCENARIOS)} scenarios).")
