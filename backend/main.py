import csv
import hashlib
import hmac
import io
import json
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
import notes
import whatif
from bms import FAULTS as BMS_FAULTS
from graph import graph
from nodes.decide import CONTROLLERS
from nodes.optimize import optimizer_node
from nodes.sensing import current_weather_version, read_and_forecast_node

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
LOG_MAX_BYTES = 5_000_000
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

    def reset(self, scenario=None, seed=None, controller=None, keep_constraints=False):
        # keeps self.lock: reset runs while the lock is held
        # Weather is downloaded again if it's more than a few hours old; this run keeps
        # its version even if another session downloads newer weather later.
        self.weather_version = current_weather_version()
        self.scenario = scenario or self.scenario
        self.controller = controller or self.controller
        # Clouds and demand noise come from this seed, so a run can be repeated exactly
        # (the LLM itself can still answer differently).
        self.seed = seed if seed is not None else secrets.randbelow(1_000_000)
        self.state = {}
        self.rule_state = {}          # the fixed-rule baseline runs through the same pipeline
        if keep_constraints and hasattr(self, "outages"):
            # The new run starts at 00:00 on day 1: keep each constraint at the same time of day
            # relative to today (e.g. "power cut today 19:00-22:00" stays 19:00-22:00 on day 1).
            shift = self.sim_hour - self.sim_hour % 24
            self.outages = [[s - shift, e - shift] for s, e in self.outages if e - shift > 0]
            self.soc_targets = [{**t, "hour": t["hour"] - shift} for t in self.soc_targets if t["hour"] - shift > 0]
            self.dr_events = [{**d, "start": d["start"] - shift, "end": d["end"] - shift}
                              for d in self.dr_events if d["end"] - shift > 0]
        else:
            self.outages = []         # [start, end) sim-hour power-cut windows for this run
            self.soc_targets = []     # operator targets {"hour", "min_pct"}
            self.dr_events = []       # demand response {"start", "end", "max_grid_kw"}
            self.bms_fault = None     # injected BMS fault for testing
        self.history = []
        self.cycle_counter = 0
        self.sim_hour = 0

    def run_inputs(self):
        """Inputs that both the chosen controller and the baseline see each hour."""
        return {"sim_hour": self.sim_hour, "scenario": self.scenario, "seed": self.seed,
                "weather_version": self.weather_version,
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
        session = _sessions.get(key)
    # A new session may download weather, so it's built outside the lock that every request uses.
    new = Session() if session is None else None
    with _sessions_lock:
        session = _sessions.pop(key, None) or new
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
    keep_constraints: bool = False   # carry power cuts/targets into the new run (same time of day)


class SimulateOptions(BaseModel):
    scenario: str = config.DEFAULT_SCENARIO
    days: int = 1
    seed: Optional[int] = None
    controller: Optional[str] = None


class ControllerOptions(BaseModel):
    controller: str


def _bad_request(message, status_code=400):
    return JSONResponse(status_code=status_code, content={"error": message})


def _invalid_controller(controller):
    return _bad_request(f"Unknown controller '{controller}'. Valid options: {list(CONTROLLERS)}")


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
    # A long-running demo server would otherwise grow the log forever: past the limit,
    # the current log becomes the one backup (replacing the older one) and a new log starts.
    try:
        if os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
    except OSError:
        pass   # no log yet, or another request just rotated it
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
    return _bad_request(f"Unknown scenario '{scenario}'. Valid options: {list(config.WEATHER_SCENARIOS.keys())}")


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
        return _bad_request("days must be between 1 and 7")
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
        return _bad_request("No cycles yet — run at least one cycle first.", 404)
    return PlainTextResponse("".join(format_log_entry(e) for e in history),
                             headers={"Content-Disposition": "attachment; filename=surya_saarthi_log.txt"})


@app.get("/history/csv")
def download_csv(x_session_id: Optional[str] = Header(None), session: Optional[str] = Query(None)):
    """Per-hour results (agent and rule-based side by side) for charts and reports."""
    history = session_from(x_session_id, session).history
    if not history:
        return _bad_request("No cycles yet — run a simulation first.", 404)
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
    keep = options.keep_constraints if options else False
    if scenario and scenario not in config.WEATHER_SCENARIOS:
        return _invalid_scenario(scenario)
    if controller and controller not in CONTROLLERS:
        return _invalid_controller(controller)
    session = session_from(x_session_id)
    if (limited := _rate_limited(session)):
        return limited
    with session.lock:
        session.reset(scenario, seed, controller, keep_constraints=keep)
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


class WeatherOptions(BaseModel):
    scenario: str


@app.post("/weather")
def set_weather(options: WeatherOptions, x_session_id: Optional[str] = Header(None)):
    """Switch the weather scenario from the next hour on, without clearing the run."""
    if options.scenario not in config.WEATHER_SCENARIOS:
        return _invalid_scenario(options.scenario)
    session = session_from(x_session_id)
    with session.lock:
        session.scenario = options.scenario
        return {"scenario": session.scenario}


# --- Operator notes, constraints, BMS faults (v2 Phase 2) ---

class NoteText(BaseModel):
    text: str


class NoteActions(BaseModel):
    actions: list


class ClearOptions(BaseModel):
    kind: Optional[str] = None      # "outage", "soc_target", "dr" or None for all


def _constraints(session):
    return {"now_hour": session.sim_hour, "outages": session.outages, "soc_targets": session.soc_targets,
            "dr_events": session.dr_events, "bms_fault": session.bms_fault}


@app.post("/note/interpret")
def interpret_note(note: NoteText, x_session_id: Optional[str] = Header(None)):
    """Read an operator's note (Hindi/Hinglish/English) into checked actions. Changes nothing:
    the operator confirms with /note/apply."""
    session = session_from(x_session_id)
    if (limited := _rate_limited(session)):
        return limited
    allow_ai = _ai_blocked_reason(session) is None
    try:
        result = notes.interpret(note.text, session.sim_hour, allow_ai=allow_ai)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": str(error)})
    if result["source"] == "ai":
        session.ai_hours.add()
        _ai_hours_all_sessions.add()
    return result


@app.post("/note/apply")
def apply_note(body: NoteActions, x_session_id: Optional[str] = Header(None)):
    session = session_from(x_session_id)
    with session.lock:
        try:
            actions = notes.validate(body.actions, session.sim_hour)
        except (ValueError, KeyError, TypeError) as error:
            return JSONResponse(status_code=400, content={"error": f"Invalid action: {error}"})
        for a in actions:
            if a["type"] == "outage":
                session.outages.append([a["start"], a["end"]])
            elif a["type"] == "soc_target":
                session.soc_targets.append({"hour": a["hour"], "min_pct": a["min_pct"]})
            elif a["type"] == "dr":
                session.dr_events.append({"start": a["start"], "end": a["end"], "max_grid_kw": a["max_grid_kw"]})
        return _constraints(session)


@app.get("/constraints")
def get_constraints(x_session_id: Optional[str] = Header(None)):
    return _constraints(session_from(x_session_id))


@app.post("/constraints/clear")
def clear_constraints(options: Optional[ClearOptions] = None, x_session_id: Optional[str] = Header(None)):
    session = session_from(x_session_id)
    kind = options.kind if options else None
    with session.lock:
        if kind in (None, "outage"):
            session.outages = []
        if kind in (None, "soc_target"):
            session.soc_targets = []
        if kind in (None, "dr"):
            session.dr_events = []
        if kind in (None, "bms_fault"):
            session.bms_fault = None
        return _constraints(session)


class FaultOptions(BaseModel):
    fault: Optional[str] = None     # "overtemp", "sensor_lost" or None to clear


@app.post("/bms/fault")
def inject_bms_fault(options: FaultOptions, x_session_id: Optional[str] = Header(None)):
    """Inject a battery fault (testing/demo) to show the system backing off safely."""
    if options.fault is not None and options.fault not in BMS_FAULTS:
        return JSONResponse(status_code=400, content={"error": f"Unknown fault. Valid: {list(BMS_FAULTS)}"})
    session = session_from(x_session_id)
    with session.lock:
        session.bms_fault = options.fault
        return _constraints(session)


# --- What-if (v2 Phase 2) ---

class WhatIfOptions(BaseModel):
    solar_scale: Optional[float] = None
    battery_health_pct: Optional[float] = None
    peak_multiplier: Optional[float] = None
    extra_load_kw: Optional[float] = None
    outage: Optional[dict] = None       # {"start": hour 0-23, "end": hour 0-23}
    dr: Optional[dict] = None           # {"start", "end", "max_grid_kw"}


@app.post("/whatif")
def run_what_if(options: WhatIfOptions, x_session_id: Optional[str] = Header(None)):
    """Next 24 hours under changed conditions vs now; optimizer and fixed rule; no AI calls."""
    session = session_from(x_session_id)
    if (limited := _rate_limited(session)):
        return limited
    with session.lock:
        try:
            return whatif.what_if(session.state, session.run_inputs(), options.model_dump(exclude_none=True))
        except (ValueError, KeyError, TypeError) as error:
            return _bad_request(f"Invalid what-if: {error}")


# --- 24 h plan for an edge device (v2 Phase 3) ---

@app.get("/plan")
def get_plan(x_session_id: Optional[str] = Header(None), session: Optional[str] = Query(None),
             x_api_key: Optional[str] = Header(None)):
    """The optimizer's schedule for the next 24 hours. A site controller caches it and
    follows it (with its own safety rules) if the connection drops. Signed when
    PLAN_SIGNING_KEY is set; requires X-Api-Key when DEVICE_API_KEY is set."""
    if config.DEVICE_API_KEY and not hmac.compare_digest(x_api_key or "", config.DEVICE_API_KEY):
        return JSONResponse(status_code=401, content={"error": "Missing or wrong X-Api-Key."})
    s = session_from(x_session_id, session)
    with s.lock:
        state = read_and_forecast_node({**{k: v for k, v in s.state.items() if k not in ("decision", "report", "plan")},
                                        **s.run_inputs()})
        state = optimizer_node(state)
    plan = state.get("plan")
    if not plan:
        return JSONResponse(status_code=503, content={"error": "No plan could be made; the device should use its fixed rule."})
    h, start = plan["hourly"], plan["start_hour"]
    schedule = [{"sim_hour": start + k, "hour": (start + k) % 24,
                 "battery_kw": round(h["d"][k] - h["sc"][k] - h["gc"][k], 2), "grid_kw": h["g"][k],
                 "genset_kw": round(h["gl"][k] + h["gc"][k], 2), "soc_pct": plan["soc_pct"][k],
                 "grid_available": plan["grid_available"][k]} for k in range(len(h["d"]))]
    payload = {"issued_at": datetime.now().isoformat(timespec="seconds"), "start_hour": start,
               "schedule": schedule, "jobs": plan["job_hour"],
               "fallback": "If the schedule is stale or its signature fails: solar, then battery above the reserve, then grid/genset."}
    body = {"plan": payload}
    if config.PLAN_SIGNING_KEY:
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        body.update(algorithm="HMAC-SHA256",
                    signature=hmac.new(config.PLAN_SIGNING_KEY.encode(), message, hashlib.sha256).hexdigest())
    return body
