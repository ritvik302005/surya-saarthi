"""The optimizer as a pipeline controller: plan 24 hours, apply the first, explain it."""
import traceback

import config
from explain import build_facts, explain
from nodes.sensing import ESSENTIAL_LOAD_PROFILE_KW, JOB_TYPES, in_outage
from optimizer import Job, PlanInputs, solve


def _allowed_hours(first, hours_to_deadline, grid_ok, horizon):
    """Hours a one-hour job may run: from `first` until the hour before its deadline,
    not during a power cut, except its very last hour (then it must run)."""
    last = first + max(1, hours_to_deadline) - 1
    hours = [k for k in range(first, min(horizon, last + 1)) if grid_ok[k] or k == last]
    return hours, last >= horizon


def plan_inputs(state):
    start = state.get("sim_hour", 0)
    H = config.PLAN_HORIZON_HOURS
    extra = state.get("extra_load_kw", 0.0)
    forecast = list(state.get("solar_forecast_next_hours") or [])
    solar = [state["solar_kw"]] + (forecast + [0.0] * H)[:H - 1]
    essential = [state["critical_load_kw"]] + [ESSENTIAL_LOAD_PROFILE_KW[(start + k) % 24] + extra for k in range(1, H)]
    price = [config.grid_price_for_hour((start + k) % 24, state.get("peak_multiplier")) for k in range(H)]
    grid_ok = [not in_outage(state.get("outages", []), start + k) for k in range(H)]

    bms = state.get("bms") or {}
    derated = bool(bms.get("alarms"))   # a temperature/fault limit holds for the whole plan
    nominal_c, nominal_d = config.BATTERY_MAX_CHARGE_KW, config.BATTERY_MAX_DISCHARGE_KW
    max_c = [bms.get("max_charge_kw", nominal_c)] + [bms.get("max_charge_kw", nominal_c) if derated else nominal_c] * (H - 1)
    max_d = [bms.get("max_discharge_kw", nominal_d)] + [bms.get("max_discharge_kw", nominal_d) if derated else nominal_d] * (H - 1)

    jobs = []
    for load in state.get("flexible_loads", []):
        to_deadline = (load["deadline_hour"] - start) % 24
        hours, beyond = _allowed_hours(0, to_deadline, grid_ok, H)
        jobs.append(Job(load["name"], load["power_kw"], hours, pending=True))
    for k in range(1, H):
        hour = (start + k) % 24
        for name, power, arrivals, deadline in JOB_TYPES:
            if hour in arrivals:
                hours, beyond = _allowed_hours(k, (deadline - hour) % 24, grid_ok, H)
                # A job whose deadline is past the horizon can still run later, at roughly normal price.
                miss = power * config.BASE_TARIFF_RS_PER_KWH if beyond else None
                # "(expected)" keeps a future arrival distinct from a waiting job with the same hour
                jobs.append(Job(f"{name} ({hour:02d}:00, expected)", power, hours, pending=False,
                                **({"miss_cost": miss} if miss is not None else {})))

    targets = [(t["hour"] - start - 1, t["min_pct"]) for t in state.get("soc_targets", [])
               if 0 <= t["hour"] - start - 1 < H]
    caps = [(k, e["max_grid_kw"]) for e in state.get("dr_events", []) for k in range(H)
            if e["start"] <= start + k < e["end"]]
    return PlanInputs(start, solar, essential, price, grid_ok, state["battery_soc_pct"],
                      state["battery_capacity_kwh"], max_c, max_d, jobs, targets, caps)


def optimizer_node(state):
    alerts = list(state.get("alerts", []))
    try:
        inputs = plan_inputs(state)
        plan = solve(inputs)
    except Exception:
        traceback.print_exc()
        from nodes.decide import fixed_rule_decision
        decision = fixed_rule_decision(state, "the optimizer found no plan")
        alerts.append("Optimizer fallback: no plan was found, so the fixed rule decided this hour.")
        return {**state, "decision": decision, "reasoning": decision["reasoning"], "reasoning_hi": "",
                "alerts": alerts, "ai_used": False, "ai_fallback": False}

    h = plan["hourly"]
    pending = [job.name for job in inputs.jobs if job.pending]
    decision = {
        "solar_used_kw": round(h["s"][0], 2),
        "battery_used_kw": round(h["d"][0] - h["sc"][0] - h["gc"][0], 2),
        "grid_used_kw": round(h["g"][0], 2),
        "genset_kw": round(h["gl"][0] + h["gc"][0], 2),
        "defer_loads": [name for name in pending if plan["job_hour"].get(name) != 0],
    }
    plan.update(price=inputs.price, grid_available=inputs.grid_available, solar_kw=inputs.solar_kw,
                essential_kw=inputs.essential_kw, start_hour=inputs.start_hour)
    facts = build_facts(state, plan, decision)
    reasoning, reasoning_hi = explain(facts)
    decision["reasoning"] = reasoning
    # The report step rewrites the explanation from the decision actually applied after the
    # safety check, so it can never describe something that didn't happen.
    return {**state, "decision": decision, "plan": plan, "explain_facts": facts, "reasoning": reasoning,
            "reasoning_hi": reasoning_hi, "alerts": alerts, "ai_used": False, "ai_fallback": False}
