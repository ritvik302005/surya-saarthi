import csv
import io
import os
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

import config
from graph import graph
from nodes.decide import CONTROLLERS
from nodes.sensing import refresh_irradiance_if_stale

app = FastAPI(title="Surya Saarthi API")

# Comma-separated list of sites allowed to call the API, e.g.
# FRONTEND_ORIGINS=https://microgrid-agent.vercel.app ; unset means any origin (local dev).
FRONTEND_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_DIR = "logs"
LOG_PATH = os.path.join(LOG_DIR, "surya_saarthi_log.txt")
os.makedirs(LOG_DIR, exist_ok=True)

MAX_SESSIONS = 100   # oldest idle sessions are dropped beyond this


class RollingCounter:
    """Counts events inside a sliding time window (thread-safe)."""

    def __init__(self, window_s):
        self.window_s = window_s
        self.times = deque()
        self.lock = threading.Lock()

    def count(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            while self.times and self.times[0] <= now - self.window_s:
                self.times.popleft()
            return len(self.times)

    def add(self, now=None):
        with self.lock:
            self.times.append(time.time() if now is None else now)


DAY_S = 24 * 3600
_ai_hours_all_sessions = RollingCounter(DAY_S)   # protects the shared Groq quota


class Session:
    """Everything one viewer's run needs. Each browser tab gets its own, so two
    people using the live demo at once never see each other's cycles."""

    def __init__(self, scenario=config.DEFAULT_SCENARIO, controller=config.DEFAULT_CONTROLLER):
        self.lock = threading.Lock()
        self.scenario = scenario
        self.controller = controller
        # Created once, not on reset, so resetting doesn't restore a used-up budget.
        self.ai_hours = RollingCounter(DAY_S)
        self.requests = RollingCounter(60)
        self.reset()

    def reset(self, scenario=None, seed=None, controller=None):
        # keeps self.lock: reset runs while the lock is held
        refresh_irradiance_if_stale()
        self.scenario = scenario or self.scenario
        self.controller = controller or self.controller
        # Clouds and demand noise come from this seed, so a run can be repeated exactly
        # (the LLM itself can still answer differently).
        self.seed = seed if seed is not None else secrets.randbelow(1_000_000)
        self.state = {}
        self.rule_state = {}          # the fixed-rule baseline runs through the same pipeline
        self.outages = []             # [start, end) sim-hour power-cut windows for this run
        self.soc_targets = []         # operator targets {"hour", "min_pct"}
        self.dr_events = []           # demand response {"start", "end", "max_grid_kw"}
        self.bms_fault = None         # injected BMS fault for testing
        self.history = []
        self.cycle_counter = 0
        self.sim_hour = 0

    def run_inputs(self):
        """Inputs that both the chosen controller and the baseline see each hour."""
        return {"sim_hour": self.sim_hour, "scenario": self.scenario, "seed": self.seed,
                "outages": list(self.outages), "soc_targets": list(self.soc_targets),
                "dr_events": list(self.dr_events), "bms_fault": self.bms_fault}


_sessions = OrderedDict()
_sessions_lock = threading.Lock()


def get_session(session_id):
    """Session id comes from the X-Session-Id header (or ?session= for plain
    download links). Requests without one share the "default" session, which
    keeps curl and the test scripts working."""
    key = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "")[:64] or "default"
    with _sessions_lock:
        session = _sessions.pop(key, None) or Session()
        _sessions[key] = session
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session


def session_from(x_session_id, session_query=None):
    return get_session(x_session_id or session_query)


def _rate_limited(session):
    """Per-session request limit, so one tab can't flood the server. (Session ids are
    chosen by the browser, so this is a courtesy limit; the AI budget below is what
    protects the Groq quota.)"""
    limit = config.REQUESTS_PER_MINUTE_PER_SESSION
    if limit is not None and session.requests.count() >= limit:
        return JSONResponse(status_code=429, content={
            "error": "Too many requests from this session. Wait a minute and try again."})
    session.requests.add()
    return None


def _ai_blocked_reason(session):
    """Why the LLM may not be used for the next hour, or None if it may."""
    if config.AI_HOURS_PER_DAY is not None and _ai_hours_all_sessions.count() >= config.AI_HOURS_PER_DAY:
        return "the demo's AI budget for today is used up"
    if config.AI_HOURS_PER_SESSION_PER_DAY is not None and session.ai_hours.count() >= config.AI_HOURS_PER_SESSION_PER_DAY:
        return "this session's AI budget for today is used up"
    return None


class ResetOptions(BaseModel):
    scenario: Optional[str] = None
    seed: Optional[int] = None
    controller: Optional[str] = None


class SimulateOptions(BaseModel):
    scenario: str = config.DEFAULT_SCENARIO
    days: int = 1
    seed: Optional[int] = None
    controller: Optional[str] = None


class ControllerOptions(BaseModel):
    controller: str


def _invalid_controller(controller):
    return {"error": f"Unknown controller '{controller}'. Valid options: {list(CONTROLLERS)}"}


def format_log_entry(entry):
    lines = [
        f"[{entry['timestamp']}] Cycle {entry['cycle']} (sim hour {entry['sim_hour']}, {entry['scenario']})",
        f"  Solar: {entry['solar_kw']} kW | Battery: {entry['battery_kw']} kW | "
        f"Grid: {entry['grid_kw']} kW | Load: {entry['load_kw']} kW",
        f"  Export: {entry['export_kw']} kW | Battery SOC after: {entry['battery_soc_pct']}%",
        f"  Reasoning: {entry['reasoning']}",
    ]
    lines += [f"  Alert: {a}" for a in entry["alerts"]] or ["  Alerts: none"]
    lines += [
        f"  Forecast missed: {'Yes' if entry['replanned'] else 'No'}",
        f"  Savings: Rs {entry['savings_rs']} | Carbon avoided: {entry['carbon_avoided_kg']} kg",
        "-" * 70,
    ]
    return "\n".join(lines) + "\n"


def log_cycle_to_file(entry):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(format_log_entry(entry))


def _run_one_cycle(session):
    """Shared by /cycle and /simulate so both paths build history entries,
    log to file, and inject sim_hour/scenario in exactly the same way —
    they can never drift out of sync with each other."""
    inputs = session.run_inputs()
    session.state.update(inputs, controller=session.controller,
                         ai_blocked_reason=_ai_blocked_reason(session) if session.controller == "ai" else None)
    state = graph.invoke(session.state)

    # The fixed-rule baseline: same pipeline, same seed, weather, demand and power cuts,
    # its own battery and job queue. So the comparison is fair by construction.
    session.rule_state.update(inputs, controller="fixed", ai_blocked_reason=None)
    rule_state = graph.invoke(session.rule_state)
    session.rule_state = rule_state
    rule, rule_decision = rule_state["report"], rule_state["decision"]

    session.cycle_counter += 1
    session.sim_hour += 1
    if state.get("ai_used"):
        session.ai_hours.add()
        _ai_hours_all_sessions.add()

    decision = state.get("decision", {})
    report = state.get("report", {})

    entry = {
        "cycle": session.cycle_counter,
        "sim_hour": state.get("sim_hour", 0),
        "scenario": state.get("scenario", session.scenario),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "solar_kw": decision.get("solar_used_kw", 0),
        "battery_kw": decision.get("battery_used_kw", 0),
        "grid_kw": decision.get("grid_used_kw", 0),
        "load_kw": report.get("served_load_kw", 0),
        "deferred_loads": report.get("deferred_loads", []),
        "battery_soc_pct": state.get("battery_soc_pct", 0),
        "reasoning": state.get("reasoning", ""),
        "alerts": state.get("alerts", []),
        "replanned": report.get("replanned_this_cycle", False),   # forecast missed, so planned cautiously
        "forecast_miss_kw": state.get("forecast_miss_kw"),
        "seed": session.seed,
        "savings_rs": report.get("savings_rs", 0),
        "carbon_avoided_kg": report.get("carbon_avoided_kg", 0),
        "grid_price_rs": state.get("grid_price_per_kwh", 0),
        "controller": state.get("controller", session.controller),
        "grid_available": report.get("grid_available", True),
        "agent_cost_rs": report.get("net_cost_rs", 0),        # import - export credit + battery wear + diesel
        "export_kw": report.get("export_kw", 0),
        "genset_kw": report.get("genset_kw", 0),
        "diesel_l": report.get("diesel_l", 0),
        "unserved_kw": report.get("unserved_kw", 0),
        "battery_wear_rs": report.get("battery_wear_rs", 0),
        "battery_soh_pct": round(state.get("battery_soh", 1.0) * 100, 3),
        "solar_available_kw": report.get("solar_available_kw", 0),
        "solar_self_used_kw": report.get("solar_self_used_kw", 0),
        "solar_curtailed_kw": report.get("solar_curtailed_kw", 0),
        "rule_grid_kw": rule["grid_used_kw"],
        "rule_battery_kw": rule_decision.get("battery_used_kw", 0),
        "rule_cost_rs": rule["net_cost_rs"],
        "rule_export_kw": rule["export_kw"],
        "rule_diesel_l": rule["diesel_l"],
        "rule_unserved_kw": rule["unserved_kw"],
        "rule_battery_wear_rs": rule["battery_wear_rs"],
        "rule_solar_self_used_kw": rule["solar_self_used_kw"],
        "rule_battery_soc_pct": rule_state.get("battery_soc_pct", 0),
        "ai_fallback": bool(state.get("ai_fallback")),
    }

    session.history.append(entry)
    log_cycle_to_file(entry)
    state["comparison"] = comparison_summary(session.history)
    session.state = state
    return entry


def comparison_summary(cycle_history):
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
        "grid_reduction_pct": pct(rule_grid - agent_grid, rule_grid),
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
        "agent_diesel_l": round(sum(c.get("diesel_l", 0) for c in cycle_history), 2),
        "rule_diesel_l": round(sum(c.get("rule_diesel_l", 0) for c in cycle_history), 2),
        "agent_unserved_kwh": round(sum(c.get("unserved_kw", 0) for c in cycle_history) * config.CYCLE_HOURS, 2),
        "rule_unserved_kwh": round(sum(c.get("rule_unserved_kw", 0) for c in cycle_history) * config.CYCLE_HOURS, 2),
        "agent_battery_wear_rs": round(sum(c.get("battery_wear_rs", 0) for c in cycle_history), 2),
        "rule_battery_wear_rs": round(sum(c.get("rule_battery_wear_rs", 0) for c in cycle_history), 2),
        "power_cut_hours": sum(1 for c in cycle_history if not c.get("grid_available", True)),
        "ai_fallback_hours": sum(1 for c in cycle_history if c["ai_fallback"]),
        "safety_override_hours": sum(1 for c in cycle_history if any(a.startswith("Safety override") for a in c["alerts"])),
    }


def _invalid_scenario(scenario):
    return {"error": f"Unknown scenario '{scenario}'. Valid options: {list(config.WEATHER_SCENARIOS.keys())}"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/scenarios")
def get_scenarios():
    """So a frontend dropdown never has to hardcode scenario names/labels."""
    return {"scenarios": {k: v["label"] for k, v in config.WEATHER_SCENARIOS.items()},
            "default": config.DEFAULT_SCENARIO}


@app.get("/state")
def get_state(x_session_id: Optional[str] = Header(None)):
    return session_from(x_session_id).state


@app.post("/cycle")
def run_cycle(x_session_id: Optional[str] = Header(None)):
    """Advances exactly one simulated hour using the session's current scenario."""
    session = session_from(x_session_id)
    if (limited := _rate_limited(session)):
        return limited
    with session.lock:
        _run_one_cycle(session)
        return session.state


@app.post("/simulate")
def simulate(options: SimulateOptions, x_session_id: Optional[str] = Header(None)):
    """Run a whole batch (days * 24 simulated hours) in one call with a chosen
    weather scenario. Always starts from a clean session, so a run is
    self-contained and repeatable for a given scenario/days."""
    if options.scenario not in config.WEATHER_SCENARIOS:
        return _invalid_scenario(options.scenario)
    if options.days < 1 or options.days > 7:
        return {"error": "days must be between 1 and 7"}
    if options.controller and options.controller not in CONTROLLERS:
        return _invalid_controller(options.controller)

    session = session_from(x_session_id)
    if (limited := _rate_limited(session)):
        return limited
    with session.lock:
        session.reset(options.scenario, options.seed, options.controller)
        total_hours = options.days * 24
        for _ in range(total_hours):
            _run_one_cycle(session)

        history = session.history
        return {
            "scenario": options.scenario,
            "days": options.days,
            "seed": session.seed,
            "controller": session.controller,
            "hours_run": total_hours,
            "summary": {
                "total_savings_rs": round(sum(c["savings_rs"] for c in history), 2),
                "total_carbon_avoided_kg": round(sum(c["carbon_avoided_kg"] for c in history), 2),
                "cycles_with_replan": sum(1 for c in history if c["replanned"]),   # hours planned cautiously after a forecast miss
                "deferred_load_events": sum(len(c["deferred_loads"]) for c in history),
                "final_battery_soc_pct": session.state.get("battery_soc_pct", 0),
                "vs_rule_based": comparison_summary(history),
            },
            "cycles": history,
            "final_state": session.state,
        }


@app.get("/history")
def get_history(x_session_id: Optional[str] = Header(None)):
    return {"cycles": session_from(x_session_id).history}


@app.get("/history/download")
def download_log(x_session_id: Optional[str] = Header(None), session: Optional[str] = Query(None)):
    """This session's cycles as a readable text log."""
    history = session_from(x_session_id, session).history
    if not history:
        return {"error": "No cycles yet — run at least one cycle first."}
    return PlainTextResponse("".join(format_log_entry(e) for e in history),
                             headers={"Content-Disposition": "attachment; filename=surya_saarthi_log.txt"})


@app.get("/history/csv")
def download_csv(x_session_id: Optional[str] = Header(None), session: Optional[str] = Query(None)):
    """Per-hour results (agent and rule-based side by side) for charts and reports."""
    history = session_from(x_session_id, session).history
    if not history:
        return {"error": "No cycles yet — run a simulation first."}
    fields = ["cycle", "sim_hour", "scenario", "controller", "grid_available", "solar_available_kw", "solar_kw",
              "battery_kw", "grid_kw", "export_kw", "genset_kw", "diesel_l", "unserved_kw", "load_kw",
              "battery_soc_pct", "battery_soh_pct", "battery_wear_rs", "grid_price_rs", "agent_cost_rs",
              "rule_grid_kw", "rule_battery_kw", "rule_export_kw", "rule_diesel_l", "rule_unserved_kw",
              "rule_battery_soc_pct", "rule_cost_rs",
              "savings_rs", "carbon_avoided_kg", "replanned", "forecast_miss_kw", "ai_fallback", "seed"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(history)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=surya_saarthi_results.csv"})


@app.post("/reset")
def reset_state(options: Optional[ResetOptions] = None, x_session_id: Optional[str] = Header(None)):
    """Clears this session. Optionally pass {"scenario": "cloudy"} to switch the
    weather scenario for the next cycles."""
    scenario = options.scenario if options else None
    seed = options.seed if options else None
    controller = options.controller if options else None
    if scenario and scenario not in config.WEATHER_SCENARIOS:
        return _invalid_scenario(scenario)
    if controller and controller not in CONTROLLERS:
        return _invalid_controller(controller)
    session = session_from(x_session_id)
    if (limited := _rate_limited(session)):
        return limited
    with session.lock:
        session.reset(scenario, seed, controller)
        return {"status": "reset", "scenario": session.scenario, "seed": session.seed, "controller": session.controller}


@app.post("/controller")
def set_controller(options: ControllerOptions, x_session_id: Optional[str] = Header(None)):
    """Switch who decides from the next hour on: "optimizer", "ai" (LLM) or "fixed"."""
    if options.controller not in CONTROLLERS:
        return _invalid_controller(options.controller)
    session = session_from(x_session_id)
    with session.lock:
        session.controller = options.controller
        return {"controller": session.controller}
