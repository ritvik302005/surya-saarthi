"""Fetch recorded weather for the benchmark and save it to data/weather_delhi.json.

For each window, hourly (IST):
  actual_*   = Open-Meteo Historical Weather API (ERA5 reanalysis; a model of what
               happened, not a ground station)
  forecast_* = Open-Meteo Previous Runs API, "_previous_day1": the forecast issued the
               day before for that hour, so forecast errors are real day-ahead errors.
Weather data by Open-Meteo.com (CC BY 4.0).

Run from backend:  python data/fetch_weather.py
"""
import json
import os
from datetime import date, timedelta

import requests

LAT, LON = 28.6139, 77.2090          # Delhi, same as config.LATITUDE/LONGITUDE
DAYS = 7                              # simulated days per window
WINDOWS = {                           # one week per season, plus one extra day for the 24 h plan horizon
    "winter": date(2026, 1, 12),
    "summer": date(2026, 5, 11),
    "monsoon": date(2026, 7, 13),
    "post-monsoon": date(2026, 9, 7),
}
OUT = os.path.join(os.path.dirname(__file__), "weather_delhi.json")


def _get(url, params):
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()["hourly"]


def _clean(values):
    """Replace missing values with the previous hour's value (0 at the start)."""
    out, last = [], 0.0
    for v in values:
        last = last if v is None else float(v)
        out.append(last)
    return out


def fetch_window(start):
    end = start + timedelta(days=DAYS)          # inclusive: DAYS + 1 days of data
    common = {"latitude": LAT, "longitude": LON, "start_date": start.isoformat(),
              "end_date": end.isoformat(), "timezone": "Asia/Kolkata"}
    actual = _get("https://archive-api.open-meteo.com/v1/archive",
                  {**common, "hourly": "shortwave_radiation,temperature_2m"})
    forecast = _get("https://previous-runs-api.open-meteo.com/v1/forecast",
                    {**common, "hourly": "shortwave_radiation_previous_day1,temperature_2m_previous_day1"})
    assert actual["time"] == forecast["time"], "archive and forecast hours don't line up"
    return {
        "start": actual["time"][0],
        "hours": len(actual["time"]),
        "actual_ghi": _clean(actual["shortwave_radiation"]),
        "actual_temp": _clean(actual["temperature_2m"]),
        "forecast_ghi": _clean(forecast["shortwave_radiation_previous_day1"]),
        "forecast_temp": _clean(forecast["temperature_2m_previous_day1"]),
    }


if __name__ == "__main__":
    data = {"source": "Open-Meteo Historical Weather API (actual, ERA5) + Previous Runs API (day-ahead forecast)",
            "licence": "CC BY 4.0, weather data by Open-Meteo.com", "latitude": LAT, "longitude": LON,
            "days_per_window": DAYS, "windows": {}}
    for name, start in WINDOWS.items():
        data["windows"][name] = fetch_window(start)
        w = data["windows"][name]
        print(f"{name}: {w['start']} +{w['hours']} h, sun kWh/m2 actual {sum(w['actual_ghi'])/1000:.1f} "
              f"vs forecast {sum(w['forecast_ghi'])/1000:.1f}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"wrote {OUT}")
