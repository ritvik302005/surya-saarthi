CYCLE_HOURS = 1.0               # each planning cycle represents one simulated hour (sim_hour advances by 1)
BATTERY_RESERVE_PCT = 20.0      # never discharge the battery below this level
DEVIATION_THRESHOLD_KW = 1.0    # forecast vs actual gap that triggers a replan

# --- LLM + impact accounting ---
LLM_MODEL = "openai/gpt-oss-20b"        # Groq model used by the allocate node
LLM_MAX_ATTEMPTS = 4                    # retries on rate limits / malformed JSON before the safe fallback kicks in
GRID_EMISSION_FACTOR_KG_PER_KWH = 0.71  # India grid average, CEA CO2 Baseline Database v21.0 (Nov 2025)

# --- Site + hardware, centralized (sensing.py used to hardcode these locally) ---
LATITUDE = 28.6139
LONGITUDE = 77.2090
SYSTEM_CAPACITY_KW = 10.0
BATTERY_MAX_CHARGE_KW = 5.0      # new: caps how fast the battery can absorb surplus solar
BATTERY_MAX_DISCHARGE_KW = 5.0   # new: absolute discharge-rate ceiling, on top of the reserve floor

# --- Time-of-Day grid tariff (Electricity (Rights of Consumers) Amendment Rules, 2023:
# solar hours at least 20% cheaper, peak hours at least 20% costlier than normal) ---
BASE_TARIFF_RS_PER_KWH = 8.0
TOD_MULTIPLIERS = [            # (start_hour, end_hour_exclusive, multiplier, label)
    (9, 17, 0.8, "solar hours"),
    (18, 22, 1.2, "peak"),
]


def grid_price_for_hour(hour_of_day):
    for start, end, multiplier, _ in TOD_MULTIPLIERS:
        if start <= hour_of_day < end:
            return round(BASE_TARIFF_RS_PER_KWH * multiplier, 2)
    return BASE_TARIFF_RS_PER_KWH


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