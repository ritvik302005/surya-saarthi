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
    previous_forecast_kw: Optional[float]
    decision: Dict
    reasoning: str
    deviation_detected: bool
    replanned: bool
    alerts: List[str]
    report: Dict