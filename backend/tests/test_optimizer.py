"""Offline checks for the 24-hour optimizer and its explanations (no Groq, no network).

Run from backend with: python tests/test_optimizer.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
import config
from explain import build_facts, explain
from nodes.optimize import optimizer_node
from optimizer import Job, PlanInputs, solve

H = 24
flat = lambda v: [v] * H


def inputs(**kw):
    base = dict(start_hour=0, solar_kw=flat(0.0), essential_kw=flat(2.0),
                price=[config.grid_price_for_hour(k) for k in range(H)], grid_available=flat(True),
                soc0_pct=60.0, capacity_kwh=10.0, max_charge_kw=flat(5.0), max_discharge_kw=flat(5.0))
    base.update(kw)
    return PlanInputs(**base)


# 1. Battery energy is saved for the expensive evening peak (18-21), not spent at night
plan = solve(inputs())
d = plan["hourly"]["d"]
assert sum(d[18:22]) > 3.0 and sum(d[0:6]) < 0.1, (d[0:6], d[18:22])

# 2. Never charged from the grid: no sun and no genset -> the battery never gains energy
assert max(plan["soc_pct"]) <= 60.0 + 0.1, plan["soc_pct"]

# 3. A known power cut 19-22: the battery is kept for it, and the grid isn't used then
cut = [not (19 <= k < 22) for k in range(H)]
plan = solve(inputs(grid_available=cut))
assert all(plan["hourly"]["g"][k] == 0 for k in range(19, 22))
assert plan["soc_pct"][18] > 50, plan["soc_pct"][18]
assert sum(plan["hourly"]["sh"]) < 0.01, "essential load left unserved although battery + genset could cover it"

# 4. A flexible job goes to the cheapest allowed hour before its deadline
job = Job("ev_charging (18:00)", 3.0, list(range(18, 24)), pending=False)
plan = solve(inputs(soc0_pct=20.0, jobs=[job]))
assert plan["job_hour"][job.name] >= 22, plan["job_hour"]      # 22:00-23:00 cost Rs 8 vs Rs 9.60 at the peak

# 5. Demand response: grid import capped at 1 kW during 18-20
plan = solve(inputs(grid_caps=[(18, 1.0), (19, 1.0)]))
assert plan["hourly"]["g"][18] <= 1.0 + 1e-6 and plan["hourly"]["g"][19] <= 1.0 + 1e-6

# 6. Operator target: at least 90% by the end of hour 15 with sun available
sunny = [max(0.0, 8 * (1 - abs(k - 12) / 6)) if 6 <= k <= 18 else 0.0 for k in range(H)]
plan = solve(inputs(solar_kw=sunny, soc0_pct=30.0, soc_targets=[(15, 90.0)]))
assert plan["soc_pct"][15] >= 89.9, plan["soc_pct"][15]

# 7. Genset minimum load: when it runs, it runs at >= 30% of its rating
plan = solve(inputs(grid_available=flat(False), soc0_pct=20.0, essential_kw=flat(0.8)))
gen = [plan["hourly"]["gl"][k] + plan["hourly"]["gc"][k] for k in range(H)]
assert all(g == 0 or g >= config.GENSET_KW * config.GENSET_MIN_LOAD_FRACTION - 1e-6 for g in gen), gen

# 8. As a pipeline controller: decision + explanation in English and Hindi, from the plan's numbers
state = {"sim_hour": 12, "solar_kw": 6.0, "solar_forecast_next_hours": sunny[13:] + flat(0.0),
         "critical_load_kw": 2.4, "flexible_loads": [], "battery_soc_pct": 50.0, "battery_capacity_kwh": 10.0,
         "outages": [[19, 22]], "alerts": []}
out = optimizer_node(state)
assert out["decision"]["battery_used_kw"] < 0, out["decision"]            # stores the sun
assert "19:00" in out["reasoning"] and "19:00" in out["reasoning_hi"], out["reasoning"]
assert "बैटरी" in out["reasoning_hi"]
en, hi = explain(build_facts({**state, "replanned": True, "forecast_miss_kw": -1.4}, out["plan"], out["decision"]))
assert "1.4 kW below forecast" in en and "1.4 kW कम" in hi, (en, hi)

print("Optimizer checks passed (peak saving, no grid charging, power cut, job shifting, DR cap, "
      "operator target, genset minimum load, English + Hindi explanations).")
