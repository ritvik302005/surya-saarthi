"""Run every weather scenario through the full agent and save the results.

Usage (from backend):  python run_scenarios.py [days]
Writes sample_results/<scenario>.json and prints a summary table. Makes real
Groq calls, so a 2-day run of all four scenarios takes a while.
"""
import json
import os
import sys

from fastapi.testclient import TestClient

import config
import main

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
OUT_DIR = "sample_results"
os.makedirs(OUT_DIR, exist_ok=True)
client = TestClient(main.app)

rows = []
for scenario in config.WEATHER_SCENARIOS:
    result = client.post("/simulate", json={"scenario": scenario, "days": DAYS},
                         headers={"X-Session-Id": f"scenario-{scenario}"}).json()
    with open(os.path.join(OUT_DIR, f"{scenario}.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    s, c = result["summary"], result["summary"]["vs_rule_based"]
    rows.append((scenario, c, s))
    print(f"done: {scenario}", flush=True)

print(f"\n{DAYS}-day runs per scenario")
header = ("scenario", "grid kWh agent/rules", "less grid", "net cost agent/rules (Rs)", "extra saved",
          "solar kWh", "self-use agent/rules", "export kWh", "CO2 avoided kg", "replans", "overrides", "AI fallbacks")
print(" | ".join(header))
for scenario, c, s in rows:
    print(" | ".join(str(x) for x in (
        scenario, f"{c['agent_grid_kwh']}/{c['rule_grid_kwh']}", f"{c['grid_reduction_pct']}%",
        f"{c['agent_cost_rs']}/{c['rule_cost_rs']}", c["extra_savings_rs"], c["solar_generated_kwh"],
        f"{c['agent_solar_self_use_pct']}%/{c['rule_solar_self_use_pct']}%", c["agent_export_kwh"],
        s["total_carbon_avoided_kg"], s["cycles_with_replan"], c["safety_override_hours"], c["ai_fallback_hours"],
    )))
