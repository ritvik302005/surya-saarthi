"""Run every weather scenario through the full agent and save the results.

Usage (from backend):  python run_scenarios.py [days]
Writes sample_results/<scenario>.json, a compact summary for the landing page
(frontend/src/data/results-summary.json) and prints a table. Makes real Groq
calls, so a 2-day run of all four scenarios takes a while.

    python run_scenarios.py --summary-only   # rebuild the summary from saved files
"""
import json
import os
import sys
from datetime import datetime

from fastapi.testclient import TestClient

import config
import main

SUMMARY_ONLY = "--summary-only" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
DAYS = int(args[0]) if args else 2
OUT_DIR = "sample_results"
SUMMARY_PATH = os.path.join("..", "frontend", "src", "data", "results-summary.json")
os.makedirs(OUT_DIR, exist_ok=True)


def essential_outage_hours(cycles):
    """Hours where solar + battery discharge + grid didn't cover the served load."""
    return sum(1 for c in cycles
               if c["solar_kw"] + max(0, c["battery_kw"]) + c["grid_kw"] < c["load_kw"] - 0.01)


def write_frontend_summary():
    scenarios = {}
    newest = 0.0
    for scenario in config.WEATHER_SCENARIOS:
        path = os.path.join(OUT_DIR, f"{scenario}.json")
        if not os.path.exists(path):
            continue
        newest = max(newest, os.path.getmtime(path))   # when the simulation actually ran
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
        c, s = result["summary"]["vs_rule_based"], result["summary"]
        days = result["days"]
        scenarios[scenario] = {
            "label": config.WEATHER_SCENARIOS[scenario]["label"],
            "days": days,
            "grid_reduction_pct": c["grid_reduction_pct"],
            "cost_reduction_pct": round(c["extra_savings_rs"] / c["rule_cost_rs"] * 100, 1) if c["rule_cost_rs"] > 0 else 0.0,
            "extra_savings_rs_per_day": round(c["extra_savings_rs"] / days, 2),
            "co2_avoided_kg_per_day": round(s["total_carbon_avoided_kg"] / days, 2),
            "solar_self_use_pct": c["agent_solar_self_use_pct"],
            "essential_outage_hours": essential_outage_hours(result["cycles"]),
            "ai_fallback_hours": c["ai_fallback_hours"],
            "hours": c["hours"],
            "replans": s["cycles_with_replan"],
        }
    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        generated_at = datetime.fromtimestamp(newest).isoformat(timespec="minutes") if scenarios else None
        json.dump({"source": "backend/run_scenarios.py", "generated_at": generated_at, "scenarios": scenarios}, f, indent=1)
    print(f"wrote {SUMMARY_PATH} ({len(scenarios)} scenarios)")


if SUMMARY_ONLY:
    write_frontend_summary()
    sys.exit(0)

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

write_frontend_summary()
