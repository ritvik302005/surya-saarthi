import math
import random
import time

import requests

import config
import physics
from bms import bms_limits

# Fetched once and cached, rather than hitting the API on every single /cycle
# call. Indexed by a simulated hour counter, not the wall clock.
_irradiance_cache = None
_temperature_cache = None
_irradiance_fetched_at = 0.0
IRRADIANCE_MAX_AGE_S = 6 * 3600

# Recorded weather for benchmarks: name -> {"actual_ghi", "actual_temp", "forecast_ghi",
# "forecast_temp"} hourly lists (index = sim_hour). "forecast_*" is the day-ahead forecast
# that was issued for those hours, so forecast errors are real ones. See data/fetch_weather.py.
WEATHER_SOURCES = {}

# Typical essential load (kW) by hour for a home / small campus block: low at
# night, a morning peak, moderate daytime, and the highest evening peak.
ESSENTIAL_LOAD_PROFILE_KW = [
    1.6, 1.5, 1.5, 1.5, 1.6, 1.8,   # 00-05 night
    2.3, 3.0, 3.1, 2.8,             # 06-09 morning peak
    2.4, 2.3, 2.4, 2.4, 2.3, 2.4,   # 10-15 daytime
    2.6, 3.0,                       # 16-17 evening ramp
    3.6, 3.8, 3.7, 3.4,             # 18-21 evening peak
    2.8, 2.1,                       # 22-23
]

# Flexible jobs: (name, power kW, arrival hours, deadline hour). Each is a one-hour job.
JOB_TYPES = [
    ("water_pump", 1.5, range(6, 10), 10),
    ("ev_charging", 3.0, range(18, 23), 6),
]


def _simulate_clear_sky_curve(hours=192):
    """Fallback used only if the live Open-Meteo call fails — a plain bell
    curve per day so the pipeline still has something physically reasonable
    to run on, instead of crashing the whole /cycle endpoint."""
    series = []
    for h in range(hours):
        hour_of_day = h % 24
        series.append(max(0.0, 850 * math.sin(math.pi * (hour_of_day - 6) / 12)) if 6 <= hour_of_day <= 18 else 0.0)
    return series


def fetch_hourly_irradiance():
    """Returns a cached list of hourly shortwave_radiation values (W/m^2)
    covering 8 days (and caches the matching air temperatures), so /simulate
    can run up to a week without re-fetching on every cycle."""
    global _irradiance_cache, _temperature_cache, _irradiance_fetched_at
    if _irradiance_cache is not None:
        return _irradiance_cache
    _irradiance_fetched_at = time.time()

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
            "hourly": "shortwave_radiation,temperature_2m", "forecast_days": 8, "timezone": "auto",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        hourly = response.json()["hourly"]
        series = hourly["shortwave_radiation"]
        if not series:
            raise ValueError("empty irradiance series in API response")
        _irradiance_cache = series
        _temperature_cache = hourly.get("temperature_2m") or None
    except Exception as e:
        print(f"[sensing] Live Open-Meteo fetch failed ({e}), using a simulated clear-sky curve instead.")
        _irradiance_cache = _simulate_clear_sky_curve()
        _temperature_cache = None

    return _irradiance_cache


def hourly_air_temp(sim_hour):
    temps = _temperature_cache
    if temps:
        value = temps[sim_hour % len(temps)]
        if value is not None:
            return value
    return config.DEFAULT_AIR_TEMP_C


def hour_rng(seed, sim_hour):
    """Random numbers for one simulated hour. Keyed on (seed, hour), so a run with the
    same seed sees exactly the same clouds and demand, and sessions never share state."""
    return random.Random(f"{seed}:{sim_hour}") if seed is not None else random.Random()


def cloud_noise(variability, rng=random):
    return min(1.25, max(0.1, rng.gauss(1.0, variability)))


def refresh_irradiance_if_stale():
    """Called when a run starts: a long-running server re-fetches the forecast
    every few hours instead of reusing the first day's data forever. Not called
    mid-run, so hour indexes stay stable within a run."""
    global _irradiance_cache
    if _irradiance_cache is not None and time.time() - _irradiance_fetched_at > IRRADIANCE_MAX_AGE_S:
        _irradiance_cache = None


def simulate_demand(sim_hour, rng=random):
    """Essential load follows a daily profile (+/-10% noise); flexible-load
    windows key off the simulated hour (wraps every 24)."""
    hour_of_day = sim_hour % 24
    critical_load_kw = round(ESSENTIAL_LOAD_PROFILE_KW[hour_of_day] * rng.uniform(0.9, 1.1), 2)
    flexible_loads = []
    # Each flexible load is a one-hour job; the start hour in the name keeps
    # jobs unique so one can be deferred while another runs.
    for name, power, arrivals, deadline in JOB_TYPES:
        if hour_of_day in arrivals:
            flexible_loads.append({"name": f"{name} ({hour_of_day:02d}:00)", "power_kw": power,
                                   "deadline": f"{deadline:02d}:00", "deadline_hour": deadline, "deferred": False})
    return critical_load_kw, flexible_loads


def hours_until_deadline(load, hour_of_day):
    return (load["deadline_hour"] - hour_of_day) % 24


def merge_flexible_loads(previous_loads, new_loads, hour_of_day):
    """Deferred jobs from last cycle are carried forward instead of silently
    vanishing (which used to count their energy as "saved"). A job in its last
    hour before the deadline is marked must_run so it can't be deferred again."""
    carried = [{**load, "deferred": False} for load in previous_loads if load.get("deferred")]
    merged = []
    for load in carried + new_loads:
        merged.append({**load, "must_run": hours_until_deadline(load, hour_of_day) <= 1})
    return merged


def in_outage(outages, sim_hour):
    """outages: list of [start_sim_hour, end_sim_hour) power-cut windows."""
    return any(start <= sim_hour < end for start, end in outages or [])


def _weather(state, sim_hour, scenario, rng):
    """(actual solar kW, air temp, raw forecast for the next hours) from recorded or live weather."""
    horizon = config.PLAN_HORIZON_HOURS - 1
    scale = state.get("solar_scale", 1.0)
    source = WEATHER_SOURCES.get(state.get("weather_source"))
    if source:
        last = len(source["actual_ghi"]) - 1
        at = lambda h: min(h, last)
        air = source["actual_temp"][at(sim_hour)]
        solar_kw = physics.pv_ac_kw(source["actual_ghi"][at(sim_hour)] * scale, air)
        forecast = [physics.pv_ac_kw(source["forecast_ghi"][at(sim_hour + k)] * scale, source["forecast_temp"][at(sim_hour + k)])
                    for k in range(1, horizon + 1)]
        return solar_kw, air, forecast
    # Live feed: the forecast is the weather API scaled for the scenario; the actual is that
    # forecast with passing-cloud noise, so the forecast can be wrong.
    series = fetch_hourly_irradiance()
    multiplier = scenario["multiplier"] * scale
    air = hourly_air_temp(sim_hour)
    actual_ghi = series[sim_hour % len(series)] * multiplier * cloud_noise(scenario["variability"], rng)
    forecast = [physics.pv_ac_kw(series[(sim_hour + k) % len(series)] * multiplier, hourly_air_temp(sim_hour + k))
                for k in range(1, horizon + 1)]
    return physics.pv_ac_kw(actual_ghi, air), air, forecast


def _corrected(state, solar_kw, raw_forecast):
    """Blend the recent actual/forecast ratio into the next hours' forecast (fading with
    distance). Returns (forecast, new ratio). Only used when enabled; see config."""
    ratio = state.get("forecast_ratio", 1.0)
    if not state.get("forecast_correction", config.FORECAST_CORRECTION):
        return raw_forecast, ratio
    raw_now = state.get("raw_forecast_next_kw")
    if raw_now is not None and raw_now > 0.5:
        observed = min(2.0, max(0.2, solar_kw / raw_now))
        ratio = (1 - config.FORECAST_CORRECTION_ALPHA) * ratio + config.FORECAST_CORRECTION_ALPHA * observed
    else:
        ratio = 1 + (ratio - 1) * 0.5   # night: let yesterday's clouds fade
    forecast = [round(min(config.INVERTER_AC_KW, max(0.0, f * (1 + (ratio - 1) * config.FORECAST_CORRECTION_DECAY ** k))), 2)
                for k, f in enumerate(raw_forecast, start=1)]
    return forecast, ratio


def read_and_forecast_node(state):
    sim_hour = state.get("sim_hour", 0)
    scenario_key = state.get("scenario", config.DEFAULT_SCENARIO)
    scenario = config.WEATHER_SCENARIOS.get(scenario_key, config.WEATHER_SCENARIOS[config.DEFAULT_SCENARIO])
    rng = hour_rng(state.get("seed"), sim_hour)

    solar_kw, air_temp, raw_forecast = _weather(state, sim_hour, scenario, rng)
    forecast, ratio = _corrected(state, solar_kw, raw_forecast)

    critical_load_kw, new_loads = simulate_demand(sim_hour, rng)
    critical_load_kw = round(critical_load_kw + state.get("extra_load_kw", 0.0), 2)
    flexible_loads = merge_flexible_loads(state.get("flexible_loads", []), new_loads, sim_hour % 24)

    # Forecast check happens here, BEFORE anything is decided: compare this hour's actual
    # sunlight with what last hour forecast for it. A big miss makes this hour's plan
    # cautious. (It used to loop back after apply and decide the hour a second time,
    # which applied the battery twice.)
    previous_forecast = state.get("forecast_solar_kw")   # what last cycle predicted for right now
    forecast_miss_kw = round(solar_kw - previous_forecast, 2) if previous_forecast is not None else None
    forecast_missed = forecast_miss_kw is not None and abs(forecast_miss_kw) > config.DEVIATION_THRESHOLD_KW

    soc = state.get("battery_soc_pct", config.INITIAL_BATTERY_SOC_PCT)
    soh = state.get("battery_soh", 1.0)
    bms = bms_limits(soc, soh, air_temp, state.get("bms_fault"))
    outages = state.get("outages", [])

    return {
        **state,
        "sim_hour": sim_hour,
        "scenario": scenario_key,
        "previous_forecast_kw": previous_forecast,
        "forecast_miss_kw": forecast_miss_kw,
        "solar_kw": solar_kw,
        "air_temp_c": air_temp,
        "forecast_solar_kw": forecast[0],
        "solar_forecast_next_hours": forecast,
        "raw_forecast_next_kw": raw_forecast[0],
        "forecast_ratio": ratio,
        "critical_load_kw": critical_load_kw,
        "flexible_loads": flexible_loads,
        "new_flexible_loads": new_loads,   # this hour's arrivals only, used by the rule-based baseline
        "battery_soc_pct": soc,
        "battery_soh": soh,
        "battery_capacity_kwh": bms["capacity_kwh"],
        "bms": bms,
        "grid_available": not in_outage(outages, sim_hour),
        "outages": outages,
        "grid_price_per_kwh": config.grid_price_for_hour(sim_hour % 24, state.get("peak_multiplier")),
        "price_band": config.price_band_for_hour(sim_hour % 24),
        # Alerts and the AI flags belong to the current cycle only.
        "alerts": [],
        "ai_used": False,
        "ai_fallback": False,
        # "replanned" keeps its old name for the API/CSV; it now means "a forecast miss
        # was detected, so this hour was planned cautiously".
        "replanned": forecast_missed,
    }
