import requests
import random
import config

# Fetched once and cached, rather than hitting the API on every single /cycle
# call — the old version called requests.get() every cycle, tied to
# datetime.now().hour, which also meant two cycles run within the same real
# clock hour returned identical solar readings. Indexing by a simulated hour
# counter instead fixes both problems at once.
_irradiance_cache = None


def _simulate_clear_sky_curve(hours=192):
    """Fallback used only if the live Open-Meteo call fails — a plain bell
    curve per day so the pipeline still has something physically reasonable
    to run on, instead of crashing the whole /cycle endpoint."""
    import math
    series = []
    for h in range(hours):
        hour_of_day = h % 24
        series.append(max(0.0, 850 * math.sin(math.pi * (hour_of_day - 6) / 12)) if 6 <= hour_of_day <= 18 else 0.0)
    return series


def fetch_hourly_irradiance():
    """Returns a cached list of hourly shortwave_radiation values (W/m^2)
    covering 8 days, so /simulate can run up to a week with headroom for the
    next-hour lookahead, without re-fetching on every cycle."""
    global _irradiance_cache
    if _irradiance_cache is not None:
        return _irradiance_cache

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": config.LATITUDE, "longitude": config.LONGITUDE,
            "hourly": "shortwave_radiation", "forecast_days": 8, "timezone": "auto",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        series = response.json()["hourly"]["shortwave_radiation"]
        if not series:
            raise ValueError("empty irradiance series in API response")
        _irradiance_cache = series
    except Exception as e:
        print(f"[sensing] Live Open-Meteo fetch failed ({e}), using a simulated clear-sky curve instead.")
        _irradiance_cache = _simulate_clear_sky_curve()

    return _irradiance_cache


def cloud_noise(variability):
    return min(1.25, max(0.1, random.gauss(1.0, variability)))


def irradiance_to_kw(irradiance_w_m2, system_capacity_kw=None):
    if system_capacity_kw is None:
        system_capacity_kw = config.SYSTEM_CAPACITY_KW
    return round(system_capacity_kw * (irradiance_w_m2 / 1000), 2)


def simulate_demand(sim_hour):
    """Same critical-load randomization as before, but flexible-load windows
    now key off the simulated hour (wraps every 24) instead of datetime.now(),
    so a scenario/day-count run produces a sensible day shape regardless of
    what time it actually is on the server."""
    hour_of_day = sim_hour % 24
    critical_load_kw = round(random.uniform(2.0, 3.5), 2)
    flexible_loads = []
    # Each flexible load is a one-hour job; the start hour in the name keeps
    # jobs unique so one can be deferred while another runs.
    if 6 <= hour_of_day <= 9:
        flexible_loads.append({"name": f"water_pump ({hour_of_day:02d}:00)", "power_kw": 1.5, "deadline": "10:00", "deadline_hour": 10, "deferred": False})
    if 18 <= hour_of_day <= 22:
        flexible_loads.append({"name": f"ev_charging ({hour_of_day:02d}:00)", "power_kw": 3.0, "deadline": "06:00", "deadline_hour": 6, "deferred": False})
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


def read_and_forecast_node(state):
    sim_hour = state.get("sim_hour", 0)
    scenario_key = state.get("scenario", config.DEFAULT_SCENARIO)
    scenario = config.WEATHER_SCENARIOS.get(scenario_key, config.WEATHER_SCENARIOS[config.DEFAULT_SCENARIO])

    series = fetch_hourly_irradiance()
    # Forecast = the weather feed scaled for the scenario. Actual = forecast with
    # passing-cloud noise, so the forecast can be wrong and the agent replans.
    forecast_now = series[sim_hour % len(series)] * scenario["multiplier"]
    current_irr = forecast_now * cloud_noise(scenario["variability"])
    next_irr = series[(sim_hour + 1) % len(series)] * scenario["multiplier"]

    critical_load_kw, new_loads = simulate_demand(sim_hour)
    flexible_loads = merge_flexible_loads(state.get("flexible_loads", []), new_loads, sim_hour % 24)

    return {
        **state,
        "sim_hour": sim_hour,
        "scenario": scenario_key,
        "previous_forecast_kw": state.get("forecast_solar_kw"),  # what last cycle predicted for right now
        "solar_kw": irradiance_to_kw(current_irr),
        "forecast_solar_kw": irradiance_to_kw(next_irr),
        "critical_load_kw": critical_load_kw,
        "flexible_loads": flexible_loads,
        "new_flexible_loads": new_loads,   # this hour's arrivals only, used by the rule-based baseline
        "battery_soc_pct": state.get("battery_soc_pct", config.INITIAL_BATTERY_SOC_PCT),
        "battery_capacity_kwh": state.get("battery_capacity_kwh", 10.0),
        "grid_price_per_kwh": config.grid_price_for_hour(sim_hour % 24),
        "price_band": config.price_band_for_hour(sim_hour % 24),
        # Alerts belong to the current cycle. A replan does not pass through
        # sensing, so both interventions from that single cycle are retained.
        "alerts": []
    }
