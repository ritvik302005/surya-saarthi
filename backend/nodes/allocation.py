import json
import math
import os
from numbers import Real

import config
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq


llm = None

SYSTEM_PROMPT = f"""You are a microgrid energy allocator. Given current solar generation,
battery state, critical load, flexible loads, and grid price, decide how to meet total
demand while minimizing grid usage, protecting battery health, and not wasting surplus solar.

Rules:
- Critical load must always be met, prioritizing solar, then battery, then grid.
- Never suggest discharging the battery below a {config.BATTERY_RESERVE_PCT:.0f}% state of charge reserve.
- If solar generation exceeds current demand, charge the battery with the surplus instead
  of wasting it. Represent charging as a NEGATIVE battery_used_kw.
- Flexible loads may be deferred if solar and battery (above reserve) cannot cover them
  without using the grid. If multiple loads must be deferred, defer the one with the
  soonest deadline_hour LAST. Loads with must_run=true are at their deadline and must
  never be deferred.
- Prefer solar over battery, and battery over grid, in that order, for serving load.

Return one JSON object with exactly these fields:
{{"solar_used_kw": <number>, "battery_used_kw": <number, negative means charging>, "grid_used_kw": <number>, "defer_loads": [<load names>], "reasoning": "<one sentence>"}}
"""

DECISION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "microgrid_allocation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "solar_used_kw": {"type": "number"},
                "battery_used_kw": {"type": "number"},
                "grid_used_kw": {"type": "number"},
                "defer_loads": {"type": "array", "items": {"type": "string"}},
                "reasoning": {"type": "string"},
            },
            "required": ["solar_used_kw", "battery_used_kw", "grid_used_kw", "defer_loads", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def _get_llm():
    global llm
    if llm is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        llm = ChatGroq(
            groq_api_key=api_key,
            model=config.LLM_MODEL,
            temperature=0,
            max_tokens=1024,
        )
    return llm


def _fallback_decision(state):
    """A deterministic allocation that always covers the critical load safely."""
    solar_for_critical = min(max(0.0, float(state["solar_kw"])), float(state["critical_load_kw"]))
    return {
        "solar_used_kw": round(solar_for_critical, 2),
        "battery_used_kw": 0.0,
        "grid_used_kw": round(max(0.0, float(state["critical_load_kw"]) - solar_for_critical), 2),
        "defer_loads": [load["name"] for load in state["flexible_loads"] if not load.get("must_run")],
        "reasoning": "Safety override applied a deterministic allocation after the allocator response was unavailable.",
    }


def _extract_json(content):
    """Accept JSON mode output plus common fenced or prose-wrapped variants."""
    if not isinstance(content, str):
        raise ValueError("LLM response content was not text")
    raw = content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start == -1:
            raise ValueError("LLM response did not contain a JSON object")
        try:
            parsed, _ = json.JSONDecoder().raw_decode(raw[start:])
        except json.JSONDecodeError as error:
            raise ValueError("LLM response contained malformed JSON") from error
        return parsed


def _validated_decision(parsed, state):
    """Reject partial or nonsensical JSON before it reaches the safety node."""
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object")
    for field in ("solar_used_kw", "battery_used_kw", "grid_used_kw"):
        value = parsed.get(field)
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError(f"LLM response has an invalid {field}")
    deferred = parsed.get("defer_loads")
    if not isinstance(deferred, list) or not all(isinstance(name, str) for name in deferred):
        raise ValueError("LLM response has an invalid defer_loads list")
    if not isinstance(parsed.get("reasoning"), str) or not parsed["reasoning"].strip():
        raise ValueError("LLM response has no reasoning")
    valid_load_names = {load["name"] for load in state["flexible_loads"]}
    if any(name not in valid_load_names for name in deferred):
        raise ValueError("LLM response tried to defer an unknown load")
    return {
        "solar_used_kw": round(float(parsed["solar_used_kw"]), 2),
        "battery_used_kw": round(float(parsed["battery_used_kw"]), 2),
        "grid_used_kw": round(float(parsed["grid_used_kw"]), 2),
        "defer_loads": deferred,
        "reasoning": parsed["reasoning"].strip(),
    }


def plan_allocation_node(state):
    flexible_summary = [
        {"name": load["name"], "power_kw": load["power_kw"], "deadline_hour": load["deadline_hour"],
         "must_run": load.get("must_run", False)}
        for load in state["flexible_loads"]
    ]
    human_prompt = f"""
Weather scenario: {state.get('scenario', 'normal')}
Simulated hour: {state.get('sim_hour', 0)} (hour-of-day {state.get('sim_hour', 0) % 24})
Solar available: {state['solar_kw']} kW
Forecast next hour: {state['forecast_solar_kw']} kW
Battery: {state['battery_soc_pct']}% of {state['battery_capacity_kwh']} kWh capacity
Critical load: {state['critical_load_kw']} kW
Flexible loads: {flexible_summary}
Grid price: Rs {state['grid_price_per_kwh']}/kWh
"""
    if state.get("replanned"):
        human_prompt += "\nThe last forecast was inaccurate. Preserve more battery reserve for uncertainty.\n"
    fallback = False
    try:
        response = _get_llm().invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human_prompt)],
            response_format=DECISION_RESPONSE_FORMAT,
        )
        parsed = _validated_decision(_extract_json(response.content), state)
    except Exception as e:
        import traceback
        print("=== ALLOCATION ERROR ===")
        traceback.print_exc()
        print("=========================")
        fallback = True
        parsed = _fallback_decision(state)
    alerts = list(state.get("alerts", []))
    if fallback:
        alerts.append(
            "Safety override: allocator output was unavailable or invalid; "
            "a deterministic safe allocation was applied."
        )
    return {**state, "decision": parsed, "reasoning": parsed["reasoning"], "alerts": alerts}