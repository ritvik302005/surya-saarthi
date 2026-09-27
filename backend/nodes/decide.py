"""The decide step of the pipeline: one of three controllers proposes this hour's
dispatch, then safety.py checks it the same way for all of them.

- "ai":        the LLM agent (nodes/allocation.py)
- "optimizer": 24-hour MILP plan (optimizer.py), first hour applied, explained from its own numbers
- "fixed":     the fixed rule a typical controller uses (the comparison baseline, and the fallback)
"""
import config
import physics

CONTROLLERS = ("optimizer", "ai", "fixed")


def fixed_rule_decision(state, why=None):
    """Solar first, then battery down to the reserve (within the BMS limit), then grid.
    Every job runs now, none deferred. In a power cut: essentials and due jobs only,
    solar -> battery -> genset."""
    grid_ok = state.get("grid_available", True)
    loads = state["flexible_loads"]
    running = [load for load in loads if grid_ok or load.get("must_run")]
    demand = float(state["critical_load_kw"]) + sum(float(load["power_kw"]) for load in running)
    solar_used = min(max(0.0, float(state["solar_kw"])), demand)
    remaining = demand - solar_used
    bms = state.get("bms") or {}
    max_dis = min(physics.max_discharge_kw(state["battery_soc_pct"], state["battery_capacity_kwh"]),
                  bms.get("max_discharge_kw", config.BATTERY_MAX_DISCHARGE_KW))
    battery = min(remaining, max_dis)
    rest = remaining - battery
    reasoning = ("The fixed rule decided this hour" + (f" ({why})" if why else "") +
                 f": solar first, then battery above the {config.BATTERY_RESERVE_PCT:.0f}% reserve, then "
                 + ("grid." if grid_ok else "genset (power cut)."))
    return {
        "solar_used_kw": round(solar_used, 2),
        "battery_used_kw": round(battery, 2),
        "grid_used_kw": round(rest, 2) if grid_ok else 0.0,
        "genset_kw": 0.0 if grid_ok else round(rest, 2),
        "defer_loads": [load["name"] for load in loads if load not in running],
        "reasoning": reasoning,
    }


def fixed_rule_node(state):
    decision = fixed_rule_decision(state)
    return {**state, "decision": decision, "reasoning": decision["reasoning"], "ai_used": False, "ai_fallback": False}


def decide_node(state):
    controller = state.get("controller", "ai")
    if controller == "fixed":
        return fixed_rule_node(state)
    if controller == "optimizer":
        from nodes.optimize import optimizer_node   # imported lazily: scipy is only needed here
        return optimizer_node(state)
    from nodes.allocation import plan_allocation_node
    return plan_allocation_node(state)
