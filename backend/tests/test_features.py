"""Offline checks for operator notes, constraints, BMS faults, what-if and the device plan.

No Groq and no network: the weather feed is the clear-sky curve and the LLM is either
absent (rule-based parser) or stubbed.
Run from backend with: python tests/test_features.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

import config
import main
import notes
import nodes.sensing as sensing

sensing.download_weather = lambda: (sensing._simulate_clear_sky_curve(), None)
config.AI_HOURS_PER_DAY = config.AI_HOURS_PER_SESSION_PER_DAY = config.REQUESTS_PER_MINUTE_PER_SESSION = None
client = TestClient(main.app)
S = {"X-Session-Id": "features"}
client.post("/reset", json={"scenario": "normal", "seed": 5}, headers=S)
for _ in range(10):                      # now it's 10:00 on day 1
    client.post("/cycle", headers=S)

# 1. Notes: rule-based parser (no AI key), Hindi and English, nothing applied until confirmed
r = client.post("/note/interpret", json={"text": "aaj shaam 7 se 10 bijli jayegi"}, headers=S).json()
assert r["source"] == "rules" and r["actions"] == [{"type": "outage", "start": 19, "end": 22}], r
assert r["summary_hi"] == ["बिजली कटौती आज 19:00 से आज 22:00 तक"], r
assert client.get("/constraints", headers=S).json()["outages"] == []            # not applied yet
assert client.post("/note/interpret", json={"text": "hello"}, headers=S).status_code == 400

# 2. Notes: an AI reading (stubbed) is validated the same way; bad actions are refused
notes.parse_ai = lambda text, now: [{"type": "soc_target", "hour": 18, "min_pct": 95.0}]
r = client.post("/note/interpret", json={"text": "shaam 6 baje tak battery full kar do"}, headers=S).json()
assert r["source"] == "ai" and r["summary_en"] == ["Battery at least 95% by today 18:00"], r
notes.parse_ai = lambda text, now: [{"type": "outage", "start": 5, "end": 30}]   # in the past + too long
assert client.post("/note/interpret", json={"text": "x"}, headers=S).status_code == 400

# 3. Apply: constraints reach the optimizer, which fills the battery before the cut
c = client.post("/note/apply", json={"actions": [{"type": "outage", "start": 19, "end": 22},
                                                 {"type": "soc_target", "hour": 18, "min_pct": 95.0}]}, headers=S).json()
assert c["outages"] == [[19, 22]] and c["soc_targets"] == [{"hour": 18, "min_pct": 95.0}], c
assert client.post("/note/apply", json={"actions": [{"type": "outage", "start": 1, "end": 3}]}, headers=S).status_code == 400
for _ in range(9):                       # run 10:00 .. 18:00
    state = client.post("/cycle", headers=S).json()
assert state["battery_soc_pct"] >= 90, state["battery_soc_pct"]
cut = client.post("/cycle", headers=S).json()                                 # 19:00, power cut
assert cut["grid_available"] is False and cut["decision"]["grid_used_kw"] == 0.0, cut["decision"]
assert "Power cut" in cut["reasoning"] and "बिजली कटौती" in cut["reasoning_hi"]

# 4. BMS fault injection: the battery is isolated and the system backs off
client.post("/bms/fault", json={"fault": "overtemp"}, headers=S)
hot = client.post("/cycle", headers=S).json()
assert hot["decision"]["battery_used_kw"] == 0.0 and any(a.startswith("BMS:") for a in hot["alerts"]), hot["alerts"]
assert client.post("/bms/fault", json={"fault": "melt"}, headers=S).status_code == 400
client.post("/bms/fault", json={"fault": None}, headers=S)
assert client.post("/constraints/clear", json={"kind": "outage"}, headers=S).json()["outages"] == []

# 5. What-if: 40% less sun costs more; an evening cut burns diesel with the fixed rule, less with the optimizer
w = client.post("/whatif", json={"solar_scale": 0.6}, headers=S).json()
assert len(w["now"]["hourly"]) == 24 and w["what_if"]["totals"]["cost_rs"] > w["now"]["totals"]["cost_rs"], w["what_if"]["totals"]
w = client.post("/whatif", json={"outage": {"start": 19, "end": 23}}, headers=S).json()
assert w["what_if"]["totals"]["unserved_kwh"] == 0, w["what_if"]["totals"]
# Fair comparison values the battery charge left at the end (the optimizer keeps more)
assert w["what_if"]["totals"]["adjusted_cost_rs"] <= w["what_if_rule"]["totals"]["adjusted_cost_rs"], (
    w["what_if"]["totals"], w["what_if_rule"]["totals"])
w = client.post("/whatif", json={"dr": {"start": 18, "end": 20, "max_grid_kw": 1.0}}, headers=S).json()
dr_hours = [x for x in w["what_if"]["hourly"] if x["hour"] in (18, 19)]
assert all(x["grid_kw"] <= 1.0 + 1e-6 for x in dr_hours), dr_hours
assert client.post("/whatif", json={"solar_scale": 9}, headers=S).status_code == 400
before = client.get("/history", headers=S).json()["cycles"]
assert len(before) == 21, len(before)                                          # what-if changed nothing

# 6. Device plan: 24 h schedule; API key and HMAC signature when configured
p = client.get("/plan", headers=S).json()
assert len(p["plan"]["schedule"]) == 24 and "signature" not in p, p.keys()
config.DEVICE_API_KEY, config.PLAN_SIGNING_KEY = "device-secret", "signing-secret"
assert client.get("/plan", headers=S).status_code == 401
p = client.get("/plan", headers={**S, "X-Api-Key": "device-secret"}).json()
message = json.dumps(p["plan"], sort_keys=True, separators=(",", ":")).encode()
assert p["signature"] == hmac.new(b"signing-secret", message, hashlib.sha256).hexdigest()
tampered = json.dumps({**p["plan"], "start_hour": 99}, sort_keys=True, separators=(",", ":")).encode()
assert p["signature"] != hmac.new(b"signing-secret", tampered, hashlib.sha256).hexdigest()
config.DEVICE_API_KEY = config.PLAN_SIGNING_KEY = None

# 7. What-if refuses an incomplete window with a clear 400 (it used to be a 500)
r = client.post("/whatif", json={"outage": {"start": 5}}, headers=S)
assert r.status_code == 400 and "start and an end" in r.json()["error"], (r.status_code, r.text)

# 8. Demand response: the optimizer keeps under the limit; any controller going over it is reported
def run_until_dr(controller):
    h = {"X-Session-Id": "dr-" + controller}
    client.post("/reset", json={"seed": 7, "controller": controller}, headers=h)
    for _ in range(18):                  # now it's 18:00
        client.post("/cycle", headers=h)
    client.post("/note/apply", json={"actions": [{"type": "dr", "start": 18, "end": 22, "max_grid_kw": 0.5}]}, headers=h)
    return client.post("/cycle", headers=h).json()

opt = run_until_dr("optimizer")
assert opt["decision"]["grid_used_kw"] <= 0.5 + 0.01 and not any(a.startswith("Demand response") for a in opt["alerts"]), opt["alerts"]
rule = run_until_dr("fixed")
assert rule["decision"]["grid_used_kw"] > 0.5 and any(a.startswith("Demand response") for a in rule["alerts"]), rule["alerts"]
assert not any(a.startswith("Safety override") for a in rule["alerts"]), rule["alerts"]   # reported, not an override

# 9. The AI is told about the limit (LLM stubbed: capture the prompt, answer with a valid decision)
import nodes.allocation as allocation
prompts = []

class Reply:
    content = json.dumps({"solar_used_kw": 0, "battery_used_kw": 0, "grid_used_kw": 0, "defer_loads": [], "reasoning": "stub"})

allocation._invoke_with_retry = lambda messages: (prompts.append(messages[-1].content), Reply())[1]
ai = run_until_dr("ai")
assert "18:00-22:00 at most 0.5 kW" in prompts[-1] and "Grid import limit now: 0.5 kW" in prompts[-1], prompts[-1]
assert "Demand response" in allocation.SYSTEM_PROMPT

# 10. A run keeps its weather: a newer download by another viewer doesn't change it mid-run
W = {"X-Session-Id": "weather-keep"}
client.post("/reset", json={"seed": 3, "controller": "fixed"}, headers=W)
for _ in range(12):                      # now it's 12:00, midday sun
    client.post("/cycle", headers=W)
sensing.download_weather = lambda: ([0.0] * 192, None)                     # the newer download has no sun at all
sensing._latest_fetched_at -= sensing.IRRADIANCE_MAX_AGE_S + 1
client.post("/reset", headers={"X-Session-Id": "weather-other"})
assert client.post("/cycle", headers=W).json()["solar_kw"] > 1.0          # still the weather this run started with
client.post("/reset", headers=W)
for _ in range(12):
    client.post("/cycle", headers=W)
assert client.post("/cycle", headers=W).json()["solar_kw"] == 0.0         # a new run uses the newer download
sensing.download_weather = lambda: (sensing._simulate_clear_sky_curve(), None)

print("Notes, constraints, BMS fault, what-if, device-plan, demand-response and weather-version checks passed.")
