CYCLE_HOURS = 1.0               # each planning cycle represents one simulated hour (sim_hour advances by 1)
BATTERY_RESERVE_PCT = 20.0      # never discharge the battery below this level
DEVIATION_THRESHOLD_KW = 1.0    # forecast vs actual gap that triggers a replan

# --- Site + hardware, centralized (sensing.py used to hardcode these locally) ---
LATITUDE = 28.6139
LONGITUDE = 77.2090
SYSTEM_CAPACITY_KW = 10.0
BATTERY_MAX_CHARGE_KW = 5.0      # new: caps how fast the battery can absorb surplus solar
BATTERY_MAX_DISCHARGE_KW = 5.0   # new: absolute discharge-rate ceiling, on top of the reserve floor

# --- Manual weather scenarios for the new /simulate + scenario-aware /reset ---
# Multiplier is applied to real Open-Meteo irradiance, so "cloudy" still tracks the
# actual shape of a day (dawn/noon/dusk) just scaled down, not an arbitrary curve.
WEATHER_SCENARIOS = {
    "sunny":   {"multiplier": 1.15, "label": "Clear sunny day"},
    "normal":  {"multiplier": 1.00, "label": "Normal / mixed clouds"},
    "cloudy":  {"multiplier": 0.55, "label": "Overcast, patchy clouds"},
    "monsoon": {"multiplier": 0.30, "label": "Heavy monsoon cloud cover"},
}
DEFAULT_SCENARIO = "normal"