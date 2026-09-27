from typing import TypedDict, List, Dict, Optional

# LangGraph drops keys that aren't declared here, so every field a node reads or
# returns must be listed.
class GridState(TypedDict, total=False):
    sim_hour: int            # simulated hour counter — replaces datetime.now(), lets /simulate run whole days
    scenario: str            # weather scenario key, see config.WEATHER_SCENARIOS
    controller: str          # "optimizer", "ai" or "fixed" (see nodes/decide.py)
    weather_source: Optional[str]   # name of recorded weather (benchmarks); None = live feed
    solar_kw: float
    air_temp_c: float
    battery_soc_pct: float
    battery_soh: float       # state of health, 1.0 = new
    battery_capacity_kwh: float   # usable capacity now (nominal x health)
    bms: Dict                # live limits and alarms from the software BMS
    bms_fault: Optional[str] # injected fault for testing ("overtemp", "sensor_lost")
    critical_load_kw: float
    extra_load_kw: float     # what-if: added essential load
    flexible_loads: List[Dict]
    new_flexible_loads: List[Dict]
    grid_price_per_kwh: float
    price_band: str
    peak_multiplier: Optional[float]   # what-if: evening-peak tariff multiplier
    grid_available: bool     # False during a power cut
    outages: List            # [start_sim_hour, end_sim_hour) power-cut windows
    soc_targets: List[Dict]  # operator targets: {"hour": sim_hour, "min_pct": ...}
    dr_events: List[Dict]    # demand response: {"start", "end", "max_grid_kw"}
    solar_scale: float       # what-if: multiply sunlight
    forecast_solar_kw: float
    solar_forecast_next_hours: List[float]
    raw_forecast_next_kw: float
    forecast_ratio: float
    forecast_correction: bool
    previous_forecast_kw: Optional[float]
    forecast_miss_kw: Optional[float]   # actual solar minus last hour's forecast for it
    seed: Optional[int]                 # makes clouds and demand repeatable for a run
    decision: Dict
    plan: Dict                          # optimizer's 24-hour plan (hourly arrays + facts)
    reasoning: str
    reasoning_hi: str                   # Hindi explanation (optimizer)
    explain_facts: Optional[Dict]       # optimizer facts, turned into the final explanation after safety
    replanned: bool                     # forecast missed by > DEVIATION_THRESHOLD_KW, so planned cautiously
    ai_blocked_reason: Optional[str]    # set by the server when the AI budget is used up
    ai_used: bool                       # the LLM was called this hour
    ai_fallback: bool                   # the fixed rule decided this hour instead of the LLM
    alerts: List[str]
    report: Dict
