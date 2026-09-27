"""Offline check that two viewers get separate sessions.

The graph is replaced with a stub so no LLM or network call is made.
Run from backend with: python test_sessions.py
"""
from fastapi.testclient import TestClient

import main


import config


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
assert "error" in client.post("/controller", json={"controller": "magic"}, headers=A).json()
client.post("/cycle", headers=A)
assert client.get("/history", headers=A).json()["cycles"][-1]["controller"] == "ai"

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

print("Session isolation, seed, AI-budget and rate-limit checks passed.")
