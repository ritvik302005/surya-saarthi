import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import csv
import io

import config
from baseline import rule_based_step
from graph import graph

app = FastAPI(title="Microgrid Load Balancer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_DIR = "logs"
LOG_PATH = os.path.join(LOG_DIR, "microgrid_log.txt")
os.makedirs(LOG_DIR, exist_ok=True)

current_state = {}
cycle_history = []   # in-memory record for this server run, cleared on /reset
cycle_counter = 0
sim_hour_counter = 0            # NEW: simulated hour, replaces datetime.now() everywhere in the pipeline
current_scenario = config.DEFAULT_SCENARIO  # NEW: manually-selectable weather scenario
baseline_soc = None             # rule-based controller's own battery, run side by side for comparison


class ResetOptions(BaseModel):
    scenario: Optional[str] = None


class SimulateOptions(BaseModel):
    scenario: str = config.DEFAULT_SCENARIO
    days: int = 1


def log_cycle_to_file(entry):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{entry['timestamp']}] Cycle {entry['cycle']} (sim hour {entry['sim_hour']}, {entry['scenario']})\n")
        f.write(f"  Solar: {entry['solar_kw']} kW | Battery: {entry['battery_kw']} kW | "
                f"Grid: {entry['grid_kw']} kW | Load: {entry['load_kw']} kW\n")
        f.write(f"  Export: {entry['export_kw']} kW | Battery SOC after: {entry['battery_soc_pct']}%\n")
        f.write(f"  Reasoning: {entry['reasoning']}\n")
        if entry["alerts"]:
            for a in entry["alerts"]:
                f.write(f"  Alert: {a}\n")
        else:
            f.write("  Alerts: none\n")
        f.write(f"  Replanned: {'Yes' if entry['replanned'] else 'No'}\n")
        f.write(f"  Savings: Rs {entry['savings_rs']} | Carbon avoided: {entry['carbon_avoided_kg']} kg\n")
        f.write("-" * 70 + "\n")


def _run_one_cycle():
    """Shared by /cycle and /simulate so both paths build history entries,
    log to file, and inject sim_hour/scenario in exactly the same way —
    they can never drift out of sync with each other."""
    global current_state, cycle_counter, sim_hour_counter, baseline_soc

    current_state["sim_hour"] = sim_hour_counter
    current_state["scenario"] = current_scenario

    current_state = graph.invoke(current_state)
    cycle_counter += 1
    sim_hour_counter += 1

    decision = current_state.get("decision", {})
    report = current_state.get("report", {})

    if baseline_soc is None:
        baseline_soc = config.INITIAL_BATTERY_SOC_PCT
    rule = rule_based_step(
        baseline_soc, current_state["battery_capacity_kwh"], current_state["solar_kw"],
        current_state["critical_load_kw"], current_state.get("new_flexible_loads", []),
        current_state["grid_price_per_kwh"],
    )
    baseline_soc = rule["soc_pct"]

    entry = {
        "cycle": cycle_counter,
        "sim_hour": current_state.get("sim_hour", 0),
        "scenario": current_state.get("scenario", current_scenario),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "solar_kw": decision.get("solar_used_kw", 0),
        "battery_kw": decision.get("battery_used_kw", 0),
        "grid_kw": decision.get("grid_used_kw", 0),
        "load_kw": report.get("served_load_kw", 0),
        "deferred_loads": report.get("deferred_loads", []),
        "battery_soc_pct": current_state.get("battery_soc_pct", 0),
        "reasoning": current_state.get("reasoning", ""),
        "alerts": current_state.get("alerts", []),
        "replanned": report.get("replanned_this_cycle", False),
        "savings_rs": report.get("savings_rs", 0),
        "carbon_avoided_kg": report.get("carbon_avoided_kg", 0),
        "grid_price_rs": current_state.get("grid_price_per_kwh", 0),
        "agent_cost_rs": report.get("net_cost_rs", 0),        # import cost minus export credit
        "export_kw": report.get("export_kw", 0),
        "solar_available_kw": report.get("solar_available_kw", 0),
        "solar_self_used_kw": report.get("solar_self_used_kw", 0),
        "solar_curtailed_kw": report.get("solar_curtailed_kw", 0),
        "rule_grid_kw": rule["grid_kw"],
        "rule_cost_rs": rule["net_cost_rs"],
        "rule_export_kw": rule["export_kw"],
        "rule_solar_self_used_kw": rule["solar_self_used_kw"],
        "ai_fallback": any("allocator output was unavailable" in a for a in current_state.get("alerts", [])),
    }

    cycle_history.append(entry)
    log_cycle_to_file(entry)
    current_state["comparison"] = comparison_summary()
    return entry


def comparison_summary():
    """Agent vs rule-based controller over every cycle run since the last reset."""
    agent_grid = sum(c["grid_kw"] for c in cycle_history) * config.CYCLE_HOURS
    rule_grid = sum(c["rule_grid_kw"] for c in cycle_history) * config.CYCLE_HOURS
    agent_cost = sum(c["agent_cost_rs"] for c in cycle_history)
    rule_cost = sum(c["rule_cost_rs"] for c in cycle_history)
    served = sum(c["load_kw"] for c in cycle_history) * config.CYCLE_HOURS
    solar = sum(c["solar_available_kw"] for c in cycle_history) * config.CYCLE_HOURS
    agent_self = sum(c["solar_self_used_kw"] for c in cycle_history) * config.CYCLE_HOURS
    rule_self = sum(c["rule_solar_self_used_kw"] for c in cycle_history) * config.CYCLE_HOURS
    pct = lambda part, whole: round(part / whole * 100, 1) if whole else 0.0
    return {
        "hours": len(cycle_history),
        "agent_grid_kwh": round(agent_grid, 2),
        "rule_grid_kwh": round(rule_grid, 2),
        "grid_reduction_pct": round((rule_grid - agent_grid) / rule_grid * 100, 1) if rule_grid else 0.0,
        "agent_cost_rs": round(agent_cost, 2),
        "rule_cost_rs": round(rule_cost, 2),
        "extra_savings_rs": round(rule_cost - agent_cost, 2),
        "renewable_share_pct": pct(served - agent_grid, served),
        "solar_generated_kwh": round(solar, 2),
        "agent_solar_self_use_pct": pct(agent_self, solar),     # solar used on site or stored, not exported
        "rule_solar_self_use_pct": pct(rule_self, solar),
        "agent_export_kwh": round(sum(c["export_kw"] for c in cycle_history) * config.CYCLE_HOURS, 2),
        "rule_export_kwh": round(sum(c["rule_export_kw"] for c in cycle_history) * config.CYCLE_HOURS, 2),
        "solar_wasted_kwh": round(sum(c["solar_curtailed_kw"] for c in cycle_history) * config.CYCLE_HOURS, 2),
        "ai_fallback_hours": sum(1 for c in cycle_history if c["ai_fallback"]),
        "safety_override_hours": sum(1 for c in cycle_history if any(
            a.startswith("Safety override") and "allocator output was unavailable" not in a for a in c["alerts"])),
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/scenarios")
def get_scenarios():
    """So a frontend dropdown never has to hardcode scenario names/labels."""
    return {"scenarios": {k: v["label"] for k, v in config.WEATHER_SCENARIOS.items()},
            "default": config.DEFAULT_SCENARIO}


@app.get("/state")
def get_state():
    return current_state


@app.post("/cycle")
def run_cycle():
    """Advances exactly one simulated hour using whatever scenario is
    currently set (via /reset, or "normal" if never set) — unchanged
    behavior from the caller's point of view, just no longer tied to the
    real wall-clock hour under the hood."""
    _run_one_cycle()
    return current_state


@app.post("/simulate")
def simulate(options: SimulateOptions):
    """NEW: run a whole batch (days * 24 simulated hours) in one call, with a
    manually chosen weather scenario — the feature this endpoint exists for.
    Starts from a clean state every time (same as calling /reset first), so
    a run is always self-contained and repeatable for a given scenario/days."""
    global current_state, cycle_history, cycle_counter, sim_hour_counter, current_scenario, baseline_soc

    if options.scenario not in config.WEATHER_SCENARIOS:
        return {"error": f"Unknown scenario '{options.scenario}'. Valid options: {list(config.WEATHER_SCENARIOS.keys())}"}
    if options.days < 1 or options.days > 7:
        return {"error": "days must be between 1 and 7"}

    current_state = {}
    cycle_history = []
    cycle_counter = 0
    sim_hour_counter = 0
    baseline_soc = None
    current_scenario = options.scenario

    total_hours = options.days * 24
    for _ in range(total_hours):
        _run_one_cycle()

    total_savings = round(sum(c["savings_rs"] for c in cycle_history), 2)
    total_carbon_avoided = round(sum(c["carbon_avoided_kg"] for c in cycle_history), 2)
    total_replans = sum(1 for c in cycle_history if c["replanned"])
    total_deferred_events = sum(len(c["deferred_loads"]) for c in cycle_history)

    return {
        "scenario": options.scenario,
        "days": options.days,
        "hours_run": total_hours,
        "summary": {
            "total_savings_rs": total_savings,
            "total_carbon_avoided_kg": total_carbon_avoided,
            "cycles_with_replan": total_replans,
            "deferred_load_events": total_deferred_events,
            "final_battery_soc_pct": current_state.get("battery_soc_pct", 0),
            "vs_rule_based": comparison_summary(),
        },
        "cycles": cycle_history,
        "final_state": current_state,
    }


@app.get("/history")
def get_history():
    return {"cycles": cycle_history}


@app.get("/history/download")
def download_log():
    if not os.path.exists(LOG_PATH):
        return {"error": "No log file yet — run at least one cycle first."}
    return FileResponse(LOG_PATH, media_type="text/plain", filename="microgrid_log.txt")


@app.get("/history/csv")
def download_csv():
    """Per-hour results (agent and rule-based side by side) for charts and reports."""
    if not cycle_history:
        return {"error": "No cycles yet — run a simulation first."}
    fields = ["cycle", "sim_hour", "scenario", "solar_available_kw", "solar_kw", "battery_kw", "grid_kw",
              "export_kw", "load_kw", "battery_soc_pct", "grid_price_rs", "agent_cost_rs",
              "rule_grid_kw", "rule_export_kw", "rule_cost_rs",
              "savings_rs", "carbon_avoided_kg", "replanned", "ai_fallback"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(cycle_history)
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=microgrid_results.csv"})


@app.post("/reset")
def reset_state(options: Optional[ResetOptions] = None):
    """Existing behavior preserved (call with no body = full reset, scenario
    stays whatever it was). NEW: optionally pass {"scenario": "cloudy"} to
    also switch the weather scenario for the manual one-cycle-at-a-time flow,
    not just the new /simulate batch endpoint."""
    global current_state, cycle_history, cycle_counter, sim_hour_counter, current_scenario, baseline_soc
    current_state = {}
    cycle_history = []
    cycle_counter = 0
    sim_hour_counter = 0
    baseline_soc = None
    if options and options.scenario:
        if options.scenario not in config.WEATHER_SCENARIOS:
            return {"error": f"Unknown scenario '{options.scenario}'. Valid options: {list(config.WEATHER_SCENARIOS.keys())}"}
        current_scenario = options.scenario
    return {"status": "reset", "scenario": current_scenario}
