import json
import math
import os
import re
import time
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
  of wasting it. Represent charging as a NEGATIVE battery_used_kw. solar_used_kw is only the
  solar that serves load; do not add the solar that goes into the battery to it.
- Flexible loads may be deferred if solar and battery (above reserve) cannot cover them
  without using the grid. If multiple loads must be deferred, defer the one with the
  soonest deadline_hour LAST. Loads with must_run=true are at their deadline and must
  never be deferred.
- Prefer solar over battery, and battery over grid, in that order, for serving load.
- Solar left over after load and battery charging is exported to the grid automatically, but
  export earns only Rs {config.EXPORT_CREDIT_RS_PER_KWH}/kWh, far less than buying power at peak,
  so storing solar for the evening is usually worth more than exporting it.
- Use the multi-hour solar forecast: if clouds are coming, keep more battery in reserve.
- Grid price changes by time of day. Save battery charge for expensive peak hours, and
  when a flexible load must use grid power, run it in a cheaper hour before its deadline
  instead of piling every deferred load into the last hour.

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
            max_tokens=2048,
            reasoning_effort="low",   # short hidden reasoning: fewer truncated JSON replies and fewer tokens per minute
            max_retries=0,            # retries are handled in _invoke_with_retry so waits can follow Groq's hints
        )
    return llm


def _retry_delay(error, attempt):
    """Groq's 429 message says how long to wait ("try again in 367.5ms" / "in 2.1s").
    Use that when present, otherwise back off exponentially."""
    match = re.search(r"try again in ([\d.]+)(ms|s)", str(error))
    if match:
        seconds = float(match.group(1)) / (1000 if match.group(2) == "ms" else 1)
        return min(seconds + 0.25, 20)
    return min(2 ** attempt, 20)


def _invoke_with_retry(messages):
    last_error = None
    for attempt in range(config.LLM_MAX_ATTEMPTS):
        try:
            response = _get_llm().invoke(messages, response_format=DECISION_RESPONSE_FORMAT)
            return response
        except Exception as error:
            last_error = error
            text = str(error)
            retryable = ("rate_limit" in text or "429" in text or "json_validate_failed" in text
                         or "503" in text or "timed out" in text.lower())
            if not retryable or attempt == config.LLM_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(error, attempt))
    raise last_error


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
    hour_now = state.get('sim_hour', 0) % 24
    upcoming_prices = ", ".join(
        f"{(hour_now + k) % 24:02d}h Rs {config.grid_price_for_hour((hour_now + k) % 24)}" for k in range(1, 9)
    )
    solar_forecast = state.get("solar_forecast_next_hours") or [state["forecast_solar_kw"]]
    solar_forecast_text = ", ".join(
        f"{(hour_now + k + 1) % 24:02d}h {kw} kW" for k, kw in enumerate(solar_forecast)
    )
    human_prompt = f"""
Weather scenario: {state.get('scenario', 'normal')}
Simulated hour: {state.get('sim_hour', 0)} (hour-of-day {state.get('sim_hour', 0) % 24})
Solar available: {state['solar_kw']} kW
Solar forecast next {len(solar_forecast)} hours: {solar_forecast_text}
Battery: {state['battery_soc_pct']}% of {state['battery_capacity_kwh']} kWh capacity
Critical load: {state['critical_load_kw']} kW
Flexible loads: {flexible_summary}
Grid price now: Rs {state['grid_price_per_kwh']}/kWh
Grid price next 8 hours: {upcoming_prices}
"""
    if state.get("replanned"):
        human_prompt += "\nThe last forecast was inaccurate. Preserve more battery reserve for uncertainty.\n"
    fallback = False
    try:
        response = _invoke_with_retry(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human_prompt)]
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