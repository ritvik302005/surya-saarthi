"""Offline check that two viewers get separate sessions.

The graph is replaced with a stub so no LLM or network call is made.
Run from backend with: python tests/test_sessions.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
from fastapi.testclient import TestClient

import main
import nodes.sensing as sensing


import config

sensing.download_weather = lambda: (sensing._simulate_clear_sky_curve(), None)   # offline


def fake_graph_invoke(state):
    hour = state.get("sim_hour", 0)
    blocked = bool(state.get("ai_blocked_reason"))   # mimic the allocator: no LLM call when blocked
    report = {"served_load_kw": 2.0, "net_cost_rs": 16.0, "grid_used_kw": 2.0, "export_kw": 0.0, "diesel_l": 0.0,
              "unserved_kw": 0.0, "battery_wear_rs": 0.0, "solar_self_used_kw": 0.0}
    ai = state.get("controller") == "ai"
    return {**state, "solar_kw": 0.0, "battery_capacity_kwh": 10.0, "critical_load_kw": 2.0,
            "new_flexible_loads": [], "grid_price_per_kwh": 8.0, "battery_soc_pct": 60.0,
            "decision": {"solar_used_kw": 0, "battery_used_kw": 0, "grid_used_kw": 2.0},
            "report": report, "alerts": [], "reasoning": f"hour {hour}",
            "ai_used": ai and not blocked, "ai_fallback": ai and blocked}


main.graph.invoke = fake_graph_invoke
config.AI_HOURS_PER_DAY = config.AI_HOURS_PER_SESSION_PER_DAY = config.REQUESTS_PER_MINUTE_PER_SESSION = None
client = TestClient(main.app)

A, B = {"X-Session-Id": "judge-a"}, {"X-Session-Id": "judge-b"}
client.post("/reset", json={"scenario": "sunny"}, headers=A)
client.post("/reset", json={"scenario": "monsoon"}, headers=B)
for _ in range(3):
    client.post("/cycle", headers=A)
client.post("/cycle", headers=B)

assert len(client.get("/history", headers=A).json()["cycles"]) == 3
assert len(client.get("/history", headers=B).json()["cycles"]) == 1
assert client.get("/state", headers=A).json()["scenario"] == "sunny"
assert client.get("/state", headers=B).json()["scenario"] == "monsoon"
assert client.get("/state", headers=B).json()["comparison"]["hours"] == 1

csv_text = client.get("/history/csv?session=judge-a").text
assert csv_text.count("\n") == 4, csv_text   # header + 3 rows

client.post("/reset", headers=A)
assert client.get("/history", headers=A).json()["cycles"] == []
assert len(client.get("/history", headers=B).json()["cycles"]) == 1

# Seeds: a chosen seed is kept and reported; without one, a random seed is picked and recorded
assert client.post("/reset", json={"seed": 42}, headers=A).json()["seed"] == 42
client.post("/cycle", headers=A)
assert client.get("/history", headers=A).json()["cycles"][0]["seed"] == 42
assert isinstance(client.post("/reset", headers=A).json()["seed"], int)
assert client.post("/simulate", json={"scenario": "sunny", "days": 1, "seed": 5}, headers=A).json()["seed"] == 5

# Controller: optimizer by default; can be switched; unknown names are rejected
assert client.post("/reset", headers=A).json()["controller"] == "optimizer"
assert client.post("/controller", json={"controller": "ai"}, headers=A).json()["controller"] == "ai"
bad = client.post("/controller", json={"controller": "magic"}, headers=A)
assert bad.status_code == 400 and "error" in bad.json(), bad.text
client.post("/cycle", headers=A)
assert client.get("/history", headers=A).json()["cycles"][-1]["controller"] == "ai"

# Weather: switching it keeps the run going (same hour count) and the next hour uses the new weather
client.post("/reset", json={"scenario": "sunny", "controller": "optimizer"}, headers=A)
client.post("/cycle", headers=A)
assert client.post("/weather", json={"scenario": "monsoon"}, headers=A).json()["scenario"] == "monsoon"
client.post("/cycle", headers=A)
cycles = client.get("/history", headers=A).json()["cycles"]
assert len(cycles) == 2 and cycles[0]["scenario"] == "sunny" and cycles[1]["scenario"] == "monsoon", cycles
assert client.post("/weather", json={"scenario": "hail"}, headers=A).status_code == 400

# Start time: a run can begin at any hour of day 1; invalid hours are rejected
assert client.post("/reset", json={"start_hour": 12}, headers=A).json()["start_hour"] == 12
assert client.post("/cycle", headers=A).json()["sim_hour"] == 12
assert client.post("/cycle", headers=A).json()["sim_hour"] == 13
assert client.post("/reset", headers=A).json()["start_hour"] == 0
assert client.post("/cycle", headers=A).json()["sim_hour"] == 0
for bad_hour in (-1, 24):
    assert client.post("/reset", json={"start_hour": bad_hour}, headers=A).status_code == 400
    assert client.post("/simulate", json={"days": 1, "start_hour": bad_hour}, headers=A).status_code == 400
sim = client.post("/simulate", json={"scenario": "sunny", "days": 1, "seed": 5, "start_hour": 9}, headers=A).json()
assert sim["cycles"][0]["sim_hour"] == 9 and len(sim["cycles"]) == 24 and sim["cycles"][-1]["sim_hour"] == 32, sim["cycles"][0]

# Per-session AI budget: after 2 AI hours, the next hour uses the fixed rule, and a reset doesn't refill it
config.AI_HOURS_PER_SESSION_PER_DAY = 2
C = {"X-Session-Id": "budget-c"}
client.post("/reset", json={"controller": "ai"}, headers=C)
for _ in range(3):
    client.post("/cycle", headers=C)
assert [c["ai_fallback"] for c in client.get("/history", headers=C).json()["cycles"]] == [False, False, True]
client.post("/reset", headers=C)
client.post("/cycle", headers=C)
assert client.get("/history", headers=C).json()["cycles"][0]["ai_fallback"] is True
config.AI_HOURS_PER_SESSION_PER_DAY = None

# Whole-demo AI budget: counts every session together
main._ai_hours_all_sessions = main.RollingCounter(main.DAY_S)
config.AI_HOURS_PER_DAY = 1
for sid in ("global-d", "global-e"):
    client.post("/controller", json={"controller": "ai"}, headers={"X-Session-Id": sid})
client.post("/cycle", headers={"X-Session-Id": "global-d"})
client.post("/cycle", headers={"X-Session-Id": "global-e"})
assert client.get("/history", headers={"X-Session-Id": "global-e"}).json()["cycles"][0]["ai_fallback"] is True
config.AI_HOURS_PER_DAY = None

# Request rate limit per session: the 4th request in a minute gets a clear 429
config.REQUESTS_PER_MINUTE_PER_SESSION = 3
F = {"X-Session-Id": "flood-f"}
codes = [client.post("/cycle", headers=F).status_code for _ in range(4)]
assert codes == [200, 200, 200, 429], codes
assert "Too many requests" in client.post("/cycle", headers=F).json()["error"]
assert client.post("/cycle", headers={"X-Session-Id": "calm-g"}).status_code == 200   # other sessions unaffected
config.REQUESTS_PER_MINUTE_PER_SESSION = None

# Status codes (SRS FR-API4): bad input is 400, downloads from an empty session are 404; the body keeps "error"
E = {"X-Session-Id": "codes-e"}
for path, body in (("/simulate", {"days": 0}), ("/simulate", {"days": 8}), ("/simulate", {"scenario": "hail"}),
                   ("/simulate", {"controller": "magic"}), ("/reset", {"scenario": "hail"}), ("/reset", {"controller": "magic"})):
    r = client.post(path, json=body, headers=E)
    assert r.status_code == 400 and "error" in r.json(), (path, body, r.status_code, r.text)
for path in ("/history/csv?session=empty-h", "/history/download?session=empty-h"):
    r = client.get(path)
    assert r.status_code == 404 and "error" in r.json(), (path, r.status_code, r.text)

# Each run keeps the weather download it started with, even after newer weather is downloaded
config.REQUESTS_PER_MINUTE_PER_SESSION = None
W1, W2 = {"X-Session-Id": "weather-1"}, {"X-Session-Id": "weather-2"}
client.post("/reset", headers=W1)
v1 = main.get_session("weather-1").weather_version
sensing._latest_fetched_at -= sensing.IRRADIANCE_MAX_AGE_S + 1          # pretend the download is old
client.post("/reset", headers=W2)                                        # another viewer's run downloads again
assert main.get_session("weather-2").weather_version == v1 + 1
assert main.get_session("weather-1").run_inputs()["weather_version"] == v1   # the first run is unaffected

print("Session isolation, seed, AI-budget, rate-limit, status-code and weather-version checks passed.")
