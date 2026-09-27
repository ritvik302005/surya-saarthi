"""What-if: replay the next 24 hours from the session's current moment under changed
conditions, without touching the session and without any AI calls.

Three runs on the same seed (same clouds and demand):
  now          the optimizer with nothing changed
  what_if      the optimizer with the changes
  what_if_rule the fixed rule with the changes (what a typical controller would do)

Changes: solar_scale (e.g. 0.6 = 40% less sun), outage (hour-of-day window), battery
health %, peak tariff multiplier, extra essential load, demand-response window.
"""
import copy

import config
from graph import graph
from optimizer import terminal_value_rs_per_kwh

HOURS = 24
LIMITS = {"solar_scale": (0.0, 1.5), "battery_health_pct": (50.0, 100.0), "peak_multiplier": (1.0, 2.0),
          "extra_load_kw": (0.0, 5.0)}


def _next(hour_of_day, now):
    sim = now - now % 24 + hour_of_day
    return sim + 24 if sim < now else sim


def check(changes):
    for key, (lo, hi) in LIMITS.items():
        if key in changes and changes[key] is not None and not lo <= float(changes[key]) <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}")
    for key in ("outage", "dr"):
        window = changes.get(key)
        if window:
            if window.get("start") is None or window.get("end") is None:
                raise ValueError(f"{key} needs both a start and an end hour")
            s, e = int(window["start"]), int(window["end"])
            if not (0 <= s <= 23 and 0 <= e <= 23 and 1 <= (e - s) % 24 <= 12):
                raise ValueError(f"{key} must be hours of day 0-23 lasting 1-12 hours")
    if changes.get("dr") and not 0 <= float(changes["dr"].get("max_grid_kw", -1)) <= 20:
        raise ValueError("dr max_grid_kw must be 0-20")


def _apply(state, changes, now):
    state = dict(state)
    if changes.get("solar_scale") is not None:
        state["solar_scale"] = float(changes["solar_scale"])
    if changes.get("peak_multiplier") is not None:
        state["peak_multiplier"] = float(changes["peak_multiplier"])
    if changes.get("extra_load_kw") is not None:
        state["extra_load_kw"] = float(changes["extra_load_kw"])
    if changes.get("battery_health_pct") is not None:
        state["battery_soh"] = float(changes["battery_health_pct"]) / 100
    if changes.get("outage"):
        s = _next(int(changes["outage"]["start"]), now)
        state["outages"] = list(state.get("outages", [])) + [[s, s + (int(changes["outage"]["end"]) - int(changes["outage"]["start"])) % 24]]
    if changes.get("dr"):
        s = _next(int(changes["dr"]["start"]), now)
        dr = {"start": s, "end": s + (int(changes["dr"]["end"]) - int(changes["dr"]["start"])) % 24,
              "max_grid_kw": float(changes["dr"]["max_grid_kw"])}
        state["dr_events"] = list(state.get("dr_events", [])) + [dr]
    return state


def _run(start_state, controller, now):
    state = {**copy.deepcopy(start_state), "controller": controller, "ai_blocked_reason": None}
    start_kwh = (state["battery_soc_pct"] / 100 * config.BATTERY_CAPACITY_KWH * state.get("battery_soh", 1.0))
    hourly, totals = [], dict(cost_rs=0.0, grid_kwh=0.0, diesel_l=0.0, unserved_kwh=0.0, export_kwh=0.0)
    for h in range(now, now + HOURS):
        state["sim_hour"] = h
        state = graph.invoke(state)
        d, r = state["decision"], state["report"]
        hourly.append({"hour": h % 24, "solar_kw": state["solar_kw"], "battery_kw": d["battery_used_kw"],
                       "grid_kw": d["grid_used_kw"], "genset_kw": d["genset_kw"], "unserved_kw": d["unserved_kw"],
                       "soc_pct": state["battery_soc_pct"], "grid_available": state["grid_available"],
                       "price": state["grid_price_per_kwh"]})
        totals["cost_rs"] += r["net_cost_rs"]
        totals["grid_kwh"] += d["grid_used_kw"]
        totals["diesel_l"] += r["diesel_l"]
        totals["unserved_kwh"] += d["unserved_kw"]
        totals["export_kwh"] += d["grid_export_kw"]
    # Fair comparison: energy added to (or taken from) the battery over the 24 hours is worth
    # something, so the adjusted cost subtracts the value of the change (same rule as the benchmark).
    end_kwh = hourly[-1]["soc_pct"] / 100 * state["battery_capacity_kwh"]
    totals["adjusted_cost_rs"] = totals["cost_rs"] - (end_kwh - start_kwh) * terminal_value_rs_per_kwh()
    totals = {k: round(v, 2) for k, v in totals.items()}
    totals["min_soc_pct"] = round(min(x["soc_pct"] for x in hourly), 1)
    totals["end_soc_pct"] = round(hourly[-1]["soc_pct"], 1)
    return {"hourly": hourly, "totals": totals}


def what_if(session_state, run_inputs, changes):
    """session_state: the session's latest state ({} before the first hour)."""
    check(changes)
    now = run_inputs["sim_hour"]
    start = {**{k: v for k, v in session_state.items() if k not in ("decision", "report", "plan", "comparison")},
             **run_inputs, "alerts": []}
    start.setdefault("battery_soc_pct", config.INITIAL_BATTERY_SOC_PCT)
    changed = _apply(start, changes, now)
    return {
        "start_hour": now % 24,
        "changes": changes,
        "now": _run(start, "optimizer", now),
        "what_if": _run(changed, "optimizer", now),
        "what_if_rule": _run(changed, "fixed", now),
    }
