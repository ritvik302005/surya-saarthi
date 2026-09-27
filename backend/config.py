import os

CYCLE_HOURS = 1.0               # each planning cycle represents one simulated hour (sim_hour advances by 1)
BATTERY_RESERVE_PCT = 20.0      # never discharge the battery below this level
INITIAL_BATTERY_SOC_PCT = 60.0  # battery level at the start of every run (agent and baseline)
DEVIATION_THRESHOLD_KW = 1.0    # forecast miss (actual vs last hour's forecast) that makes this hour's plan cautious


def _env_limit(name, default):
    """Positive integer from the environment; 0 or a negative value means no limit (None)."""
    raw = os.getenv(name, "").strip()
    value = int(raw) if raw else default
    return value if value > 0 else None


# --- Public-demo protection (set these on the server; run_scenarios.py lifts the AI limits) ---
# Groq's free tier allows ~200k tokens/day; one AI-decided hour uses roughly 1k tokens
# (estimate from past runs), so the whole demo gets 150 AI hours per rolling 24 h. Past a
# limit, hours are decided by the fixed rule instead and marked as AI fallback.
# Device endpoint (/plan): if DEVICE_API_KEY is set, callers must send it as X-Api-Key; if
# PLAN_SIGNING_KEY is set, the 24 h schedule is signed (HMAC-SHA256) so the device can check it.
DEVICE_API_KEY = os.getenv("DEVICE_API_KEY") or None
PLAN_SIGNING_KEY = os.getenv("PLAN_SIGNING_KEY") or None

AI_HOURS_PER_DAY = _env_limit("AI_HOURS_PER_DAY", 150)
AI_HOURS_PER_SESSION_PER_DAY = _env_limit("AI_HOURS_PER_SESSION_PER_DAY", 48)
REQUESTS_PER_MINUTE_PER_SESSION = _env_limit("REQUESTS_PER_MINUTE_PER_SESSION", 300)

# Who decides by default: "optimizer" (MILP plan, explained in plain words), "ai" (LLM
# decides) or "fixed" (the fixed rule). Viewers can switch on the dashboard.
DEFAULT_CONTROLLER = "optimizer"

# --- LLM + impact accounting ---
LLM_MODEL = "openai/gpt-oss-20b"        # Groq model used by the allocate node
LLM_MAX_ATTEMPTS = 6                    # retries on rate limits / malformed JSON before the safe fallback kicks in
GRID_EMISSION_FACTOR_KG_PER_KWH = 0.71  # India grid average, CEA CO2 Baseline Database v21.0 (Nov 2025)

# --- Site + hardware, centralized (sensing.py used to hardcode these locally) ---
LATITUDE = 28.6139
LONGITUDE = 77.2090
SYSTEM_CAPACITY_KW = 10.0
BATTERY_MAX_CHARGE_KW = 5.0      # new: caps how fast the battery can absorb surplus solar
BATTERY_MAX_DISCHARGE_KW = 5.0   # new: absolute discharge-rate ceiling, on top of the reserve floor

# --- Solar physics (PVWatts-style; v2 Phase 1) ---
# kW_ac = capacity x GHI/1000 x (1 - losses) x (1 + temp_coeff x (T_cell - 25)) x inverter_eff,
# capped at the inverter rating. GHI is used as-is (panel tilt ignored).
PV_SYSTEM_LOSSES = 0.14          # NREL PVWatts default total losses (soiling, wiring, mismatch, ...)
PV_TEMP_COEFF_PER_C = -0.004     # typical crystalline-silicon power coefficient (-0.4 %/degC); use your module datasheet
PV_NOCT_C = 45.0                 # typical nominal operating cell temperature; T_cell = T_air + (NOCT - 20)/800 x GHI
INVERTER_EFFICIENCY = 0.96       # PVWatts default nominal inverter efficiency
INVERTER_AC_KW = 10.0            # output never exceeds the inverter rating (clipping)
DEFAULT_AIR_TEMP_C = 30.0        # used when no temperature data is available

# --- Battery physics and wear (v2 Phase 1) ---
BATTERY_CAPACITY_KWH = 10.0
BATTERY_ROUND_TRIP_EFFICIENCY = 0.92   # ASSUMPTION: typical LFP is 90-95%; use your battery's datasheet
BATTERY_CHARGE_EFFICIENCY = BATTERY_ROUND_TRIP_EFFICIENCY ** 0.5
BATTERY_DISCHARGE_EFFICIENCY = BATTERY_ROUND_TRIP_EFFICIENCY ** 0.5
BATTERY_PRICE_RS_PER_KWH = 12000.0     # ASSUMPTION placeholder: replacement cost per kWh of capacity; put your quote here
BATTERY_CYCLE_LIFE = 4000              # ASSUMPTION: LFP datasheets commonly quote 4,000-6,000 cycles at 80% depth
BATTERY_CYCLE_DEPTH = 0.8              # depth the cycle-life figure refers to
BATTERY_END_OF_LIFE_SOH = 0.8          # capacity fraction at which the cycle life is counted as used up
# Wear cost per kWh taken out of the battery = replacement cost / lifetime kWh throughput.
BATTERY_WEAR_RS_PER_KWH = BATTERY_PRICE_RS_PER_KWH / (BATTERY_CYCLE_LIFE * BATTERY_CYCLE_DEPTH)

# --- Battery management system limits (software BMS, v2 Phase 2) ---
BMS_CHARGE_TAPER_START_PCT = 90.0      # charging tapers to zero between here and 100%
BMS_DISCHARGE_TAPER_END_PCT = 25.0     # discharge tapers to zero between here and the reserve
BMS_BATTERY_TEMP_RISE_C = 3.0          # battery room assumed this much warmer than outside air
BMS_DERATE_TEMP_C = 45.0               # above this, limits are halved
BMS_CUTOFF_TEMP_C = 55.0               # above this, the battery is disconnected
BMS_MIN_CHARGE_TEMP_C = 0.0            # LFP cells must not be charged below 0 degC

# --- Diesel genset (used during power cuts; v2 Phase 1) ---
GENSET_KW = 5.0                  # ASSUMPTION: site genset rating
GENSET_MIN_LOAD_FRACTION = 0.3   # common guidance: avoid running a diesel genset below ~30% load
DIESEL_PRICE_RS_PER_L = 90.0     # ASSUMPTION: set your local diesel price
GENSET_KWH_PER_L = 2.8           # ASSUMPTION: small genset at part load; use your genset's fuel curve
# Fuel is modelled as proportional to output: the extra fuel a genset burns just by
# running (idle / no-load consumption) is not included, so light-load hours are optimistic.
GENSET_RS_PER_KWH = DIESEL_PRICE_RS_PER_L / GENSET_KWH_PER_L
DIESEL_CO2_KG_PER_L = 2.68       # CO2 from burning one litre of diesel (standard combustion factor)
# Optimizer penalty (not a price) for leaving essential load unserved. High enough that it
# always starts the genset, even at its minimum load, rather than cut essentials, as the plant does.
VALUE_OF_LOST_LOAD_RS_PER_KWH = 1000.0

# --- Net metering (PM Surya Ghar rooftop systems can export surplus solar) ---
GRID_EXPORT_LIMIT_KW = SYSTEM_CAPACITY_KW   # can't export more than the inverter/system size
EXPORT_CREDIT_RS_PER_KWH = 3.0   # ASSUMPTION: credit per exported kWh; varies by state/DISCOM, set to your local rate
SOLAR_FORECAST_HOURS = 8         # how many hours of solar forecast the LLM agent sees
PLAN_HORIZON_HOURS = 24          # how far ahead the optimizer plans (this hour + 23)
# Forecast correction: after each daylight hour, blend the observed actual/forecast ratio
# into the next hours' forecast, fading with distance. Off unless measured to help
# (see benchmark.py): with independent hourly noise it can only make forecasts worse.
FORECAST_CORRECTION = False
FORECAST_CORRECTION_ALPHA = 0.5  # weight of the newest ratio in the running estimate
FORECAST_CORRECTION_DECAY = 0.8  # how fast the correction fades per hour ahead

# --- Time-of-Day grid tariff (Electricity (Rights of Consumers) Amendment Rules, 2023:
# solar hours at least 20% cheaper than normal; peak hours 10-20% costlier, set by each
# state; we assume 20%) ---
BASE_TARIFF_RS_PER_KWH = 8.0
TOD_MULTIPLIERS = [            # (start_hour, end_hour_exclusive, multiplier, label)
    (9, 17, 0.8, "solar hours"),
    (18, 22, 1.2, "peak"),
]


def price_band_for_hour(hour_of_day):
    for start, end, _, label in TOD_MULTIPLIERS:
        if start <= hour_of_day < end:
            return label
    return "normal"


def grid_price_for_hour(hour_of_day, peak_multiplier=None):
    """Grid price in Rs/kWh. peak_multiplier (what-if) replaces the evening-peak multiplier."""
    for start, end, multiplier, label in TOD_MULTIPLIERS:
        if start <= hour_of_day < end:
            if label == "peak" and peak_multiplier is not None:
                multiplier = peak_multiplier
            return round(BASE_TARIFF_RS_PER_KWH * multiplier, 2)
    return BASE_TARIFF_RS_PER_KWH


# --- Manual weather scenarios for the new /simulate + scenario-aware /reset ---
# Multiplier is applied to real Open-Meteo irradiance, so "cloudy" still tracks the
# actual shape of a day (dawn/noon/dusk) just scaled down, not an arbitrary curve.
# "variability" is how far actual sunlight wanders from the forecast hour to hour
# (std-dev as a fraction), so passing clouds make the forecast wrong and trigger replans.
WEATHER_SCENARIOS = {
    "sunny":   {"multiplier": 1.15, "variability": 0.05, "label": "Clear sunny day"},
    "normal":  {"multiplier": 1.00, "variability": 0.20, "label": "Normal / mixed clouds"},
    "cloudy":  {"multiplier": 0.55, "variability": 0.35, "label": "Overcast, patchy clouds"},
    "monsoon": {"multiplier": 0.30, "variability": 0.45, "label": "Heavy monsoon cloud cover"},
}
DEFAULT_SCENARIO = "normal"