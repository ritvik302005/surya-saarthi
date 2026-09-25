"""Offline check that two viewers get separate sessions.

The graph is replaced with a stub so no LLM or network call is made.
Run from backend with: python test_sessions.py
"""
from fastapi.testclient import TestClient

import main


def fake_graph_invoke(state):
    hour = state.get("sim_hour", 0)
    return {**state, "solar_kw": 0.0, "battery_capacity_kwh": 10.0, "critical_load_kw": 2.0,
            "new_flexible_loads": [], "grid_price_per_kwh": 8.0, "battery_soc_pct": 60.0,
            "decision": {"solar_used_kw": 0, "battery_used_kw": 0, "grid_used_kw": 2.0},
            "report": {"served_load_kw": 2.0, "net_cost_rs": 16.0}, "alerts": [], "reasoning": f"hour {hour}"}


main.graph.invoke = fake_graph_invoke
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

print("Session isolation checks passed.")
