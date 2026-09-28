"""Fast, offline checks for allocator response handling.

Run from backend with: python tests/test_allocation_parsing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import nodes.allocation as allocation


STATE = {
    "solar_kw": 2.0,
    "forecast_solar_kw": 2.5,
    "battery_soc_pct": 60.0,
    "battery_capacity_kwh": 10.0,
    "critical_load_kw": 3.0,
    "flexible_loads": [{"name": "water_pump", "power_kw": 1.5, "deadline_hour": 10}],
    "grid_price_per_kwh": 8.0,
    "alerts": [],
}


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLlm:
    def __init__(self, content):
        self.content = content

    def invoke(self, *_args, **_kwargs):
        return FakeResponse(self.content)


def check(content, expected_alert_count):
    allocation.llm = FakeLlm(content)
    result = allocation.plan_allocation_node(STATE)
    assert len(result["alerts"]) == expected_alert_count, result
    return result


valid = check(
    '```json\n{"solar_used_kw": 2, "battery_used_kw": 1, "grid_used_kw": 0, '
    '"defer_loads": [], "reasoning": "Solar and battery cover the critical load."}\n```',
    0,
)
assert valid["decision"]["battery_used_kw"] == 1.0

# An unusable answer falls back to the fixed rule: solar 2 kW, then battery above the
# reserve covers the remaining 3 + 1.5 - 2 = 2.5 kW, no grid, nothing deferred.
fallback = check("I cannot provide an allocation.", 1)
assert fallback["decision"] == {**fallback["decision"], "solar_used_kw": 2.0, "battery_used_kw": 2.5,
                                "grid_used_kw": 0.0, "defer_loads": []}, fallback["decision"]
assert fallback["alerts"][0].startswith("AI fallback:")
assert fallback["ai_used"] is True and fallback["ai_fallback"] is True

# Low battery: the fixed rule stops at the reserve and buys the rest from the grid
low = allocation._fallback_decision({**STATE, "battery_soc_pct": 22.0}, "test")
assert low["battery_used_kw"] == 0.19 and low["grid_used_kw"] == 2.31, low   # discharge losses

# AI budget used up: the LLM is never called
class ExplodingLlm:
    def invoke(self, *_args, **_kwargs):
        raise AssertionError("the LLM must not be called when the AI budget is used up")

allocation.llm = ExplodingLlm()
blocked = allocation.plan_allocation_node({**STATE, "ai_blocked_reason": "the demo's AI budget for today is used up"})
assert blocked["ai_used"] is False and blocked["ai_fallback"] is True, blocked
assert blocked["alerts"] == ["AI fallback: the demo's AI budget for today is used up, so the fixed rule decided this hour."]

print("Allocator parsing, fixed-rule fallback and AI-budget checks passed.")
