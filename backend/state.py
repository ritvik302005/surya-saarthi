from typing import TypedDict, List, Dict, Optional

class GridState(TypedDict):
    sim_hour: int            # simulated hour counter — replaces datetime.now(), lets /simulate run whole days
    scenario: str            # weather scenario key, see config.WEATHER_SCENARIOS
    solar_kw: float
    battery_soc_pct: float
    battery_capacity_kwh: float
    critical_load_kw: float
    flexible_loads: List[Dict]
    new_flexible_loads: List[Dict]
    grid_price_per_kwh: float
    price_band: str
    forecast_solar_kw: float
    solar_forecast_next_hours: List[float]
    previous_forecast_kw: Optional[float]
    forecast_miss_kw: Optional[float]   # actual solar minus last hour's forecast for it
    seed: Optional[int]                 # makes clouds and demand repeatable for a run
    decision: Dict
    reasoning: str
    replanned: bool                     # forecast missed by > DEVIATION_THRESHOLD_KW, so planned cautiously
    ai_blocked_reason: Optional[str]    # set by the server when the AI budget is used up
    ai_used: bool                       # the LLM was called this hour
    ai_fallback: bool                   # the fixed rule decided this hour instead of the LLM
    alerts: List[str]
    report: Dict