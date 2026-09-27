"""Benchmark: every controller on recorded Delhi weather, grid normal and with power cuts.

Weather: data/weather_delhi.json (four one-week windows, one per season; actual =
Open-Meteo ERA5 reanalysis, forecast = the day-ahead forecast issued for those hours).
Demand: the simulated profile, same seed for every controller. Each controller runs the
full pipeline (same safety, physics, BMS), each with its own battery and job queue.

Controllers
  fixed               the fixed rule (solar -> battery -> grid/genset)
  optimizer           24 h MILP with the real day-ahead forecast
  optimizer+correct   the same, with forecast correction from recent misses
  perfect             the same optimizer given the actual weather as its forecast. Shows what
                      forecast errors cost; NOT a true optimum (each hourly plan sees only 24 h)
  ai                  the LLM agent (only with --ai-days N, one season only: uses Groq quota)

Conditions
  grid normal
  evening cuts        ILLUSTRATIVE schedule: a power cut 19:00-22:00 every day

Costs include grid import, export credit, battery wear and diesel; "adjusted" also values
the change in stored battery energy at the end, so no controller gains by emptying it.

Run from backend:  python benchmark.py [--ai-days N]
Writes sample_results/benchmark.json, prints tables, updates the landing results strip.
"""
import json
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()   # GROQ_API_KEY for the optional AI runs

import config
import nodes.sensing as sensing
from graph import graph
from optimizer import terminal_value_rs_per_kwh

SEED = 1
DATA = os.path.join(os.path.dirname(__file__), "data", "weather_delhi.json")
OUT_DIR = "sample_results"
SUMMARY_PATH = os.path.join("..", "frontend", "src", "data", "results-summary.json")
AI_DAYS = int(sys.argv[sys.argv.index("--ai-days") + 1]) if "--ai-days" in sys.argv else 0
AI_WINDOW = "post-monsoon"   # the AI runs on one season only, to spare the Groq quota

config.AI_HOURS_PER_DAY = config.AI_HOURS_PER_SESSION_PER_DAY = None   # offline benchmark: no demo budget


def load_windows():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    for name, w in data["windows"].items():
        sensing.WEATHER_SOURCES[name] = w
        # Perfect foresight: the "forecast" is what actually happened.
        sensing.WEATHER_SOURCES[name + ":perfect"] = {**w, "forecast_ghi": w["actual_ghi"], "forecast_temp": w["actual_temp"]}
    return data


def evening_cuts(days):
    return [[24 * d + 19, 24 * d + 22] for d in range(days)]


def run(window, controller, hours, outages, perfect=False, correction=False):
    state = {"scenario": "normal", "seed": SEED, "controller": controller,
             "weather_source": window + (":perfect" if perfect else ""), "outages": outages,
             "forecast_correction": correction}
    totals = dict(net_cost=0.0, grid_kwh=0.0, export_kwh=0.0, diesel_l=0.0, genset_hours=0,
                  unserved_kwh=0.0, discharged_kwh=0.0, wear_rs=0.0, co2_kg=0.0, overrides=0, ai_fallback=0,
                  served_kwh=0.0)
    for h in range(hours):
        state["sim_hour"] = h
        state = graph.invoke(state)
        r, d = state["report"], state["decision"]
        totals["net_cost"] += r["net_cost_rs"]
        totals["grid_kwh"] += d["grid_used_kw"]
        totals["export_kwh"] += d["grid_export_kw"]
        totals["diesel_l"] += r["diesel_l"]
        totals["genset_hours"] += d["genset_kw"] > 0
        totals["unserved_kwh"] += d["unserved_kw"]
        totals["discharged_kwh"] += max(0.0, d["battery_used_kw"])
        totals["wear_rs"] += r["battery_wear_rs"]
        totals["served_kwh"] += r["served_load_kw"]
        totals["co2_kg"] += ((d["grid_used_kw"] - d["grid_export_kw"]) * config.GRID_EMISSION_FACTOR_KG_PER_KWH
                             + r["diesel_l"] * config.DIESEL_CO2_KG_PER_L)
        totals["overrides"] += any(a.startswith("Safety override") for a in state["alerts"])
        totals["ai_fallback"] += bool(state.get("ai_fallback"))
    stored_change = (state["battery_soc_pct"] - config.INITIAL_BATTERY_SOC_PCT) / 100 * state["battery_capacity_kwh"]
    totals["soc_end"] = state["battery_soc_pct"]
    totals["adjusted_cost"] = totals["net_cost"] - stored_change * terminal_value_rs_per_kwh()
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()}


def forecast_errors(window, hours):
    """Mean absolute error (kW, daylight hours) of the next-hour solar forecast, raw vs corrected."""
    out = {}
    for correction in (False, True):
        state, errors = {"scenario": "normal", "seed": SEED, "weather_source": window, "forecast_correction": correction}, []
        for h in range(hours):
            state = sensing.read_and_forecast_node({**state, "sim_hour": h})
            if state["previous_forecast_kw"] is not None and (state["solar_kw"] > 0.2 or state["previous_forecast_kw"] > 0.2):
                errors.append(abs(state["solar_kw"] - state["previous_forecast_kw"]))
        out["corrected" if correction else "raw"] = round(sum(errors) / len(errors), 3)
    return out


def main():
    data = load_windows()
    hours = data["days_per_window"] * 24
    days = data["days_per_window"]
    runs = [("fixed", {}), ("optimizer", {}), ("optimizer+correct", {"correction": True}), ("perfect", {"perfect": True})]
    results = {"generated_at": datetime.now().isoformat(timespec="minutes"), "seed": SEED, "days_per_window": days,
               "weather": data["source"], "conditions": {}, "forecast_mae_kw": {}}
    t0 = time.time()
    for window in data["windows"]:
        results["forecast_mae_kw"][window] = forecast_errors(window, hours)
    for condition, outages in (("grid normal", []), ("evening cuts", evening_cuts(days))):
        cond = results["conditions"].setdefault(condition, {})
        for window in data["windows"]:
            for label, opts in runs:
                controller = "fixed" if label == "fixed" else "optimizer"
                cond.setdefault(window, {})[label] = run(window, controller, hours, outages, **opts)
                print(f"{condition:12s} {window:13s} {label:18s} done ({time.time() - t0:.0f} s)", flush=True)
            if AI_DAYS and window == AI_WINDOW:
                ai = run(window, "ai", AI_DAYS * 24, outages)
                ref = {label: run(window, "fixed" if label == "fixed" else "optimizer", AI_DAYS * 24, outages)
                       for label in ("fixed", "optimizer")}
                cond[window][f"ai ({AI_DAYS} d)"] = ai
                cond[window][f"fixed ({AI_DAYS} d)"] = ref["fixed"]
                cond[window][f"optimizer ({AI_DAYS} d)"] = ref["optimizer"]
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "benchmark.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print_tables(results)
    write_summary(results)


def print_tables(results):
    for condition, windows in results["conditions"].items():
        print(f"\n## {condition} ({results['days_per_window']} days per season, seed {results['seed']})\n")
        print("| season | controller | adjusted cost Rs | net cost Rs | grid kWh | diesel L | unserved kWh | battery out kWh | CO2 kg | overrides | AI fallback h |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for window, runs in windows.items():
            for label, r in runs.items():
                print(f"| {window} | {label} | {r['adjusted_cost']} | {r['net_cost']} | {r['grid_kwh']} | {r['diesel_l']} | "
                      f"{r['unserved_kwh']} | {r['discharged_kwh']} | {r['co2_kg']} | {r['overrides']} | {r['ai_fallback']} |")
    print("\nNext-hour solar forecast error (MAE, kW, daylight):", results["forecast_mae_kw"])


def write_summary(results):
    """Headline numbers for the landing page: optimizer vs fixed rule, per condition."""
    summary = {"source": "backend/benchmark.py", "generated_at": results["generated_at"],
               "days": results["days_per_window"], "seasons": list(next(iter(results["conditions"].values()))),
               "conditions": {}}
    for condition, windows in results["conditions"].items():
        fixed = sum(w["fixed"]["adjusted_cost"] for w in windows.values())
        opt = sum(w["optimizer"]["adjusted_cost"] for w in windows.values())
        perfect = sum(w["perfect"]["adjusted_cost"] for w in windows.values())
        n_days = results["days_per_window"] * len(windows)
        summary["conditions"][condition] = {
            "cost_reduction_pct": round((fixed - opt) / fixed * 100, 1) if fixed > 0 else 0.0,
            "saved_rs_per_day": round((fixed - opt) / n_days, 1),
            "forecast_cost_pct": round((opt - perfect) / fixed * 100, 1) if fixed > 0 else 0.0,   # vs perfect forecast
            "diesel_l": {"fixed": round(sum(w["fixed"]["diesel_l"] for w in windows.values()), 1),
                         "optimizer": round(sum(w["optimizer"]["diesel_l"] for w in windows.values()), 1)},
            "unserved_kwh": round(sum(w["optimizer"]["unserved_kwh"] for w in windows.values()), 2),
            "overrides": sum(w["optimizer"]["overrides"] for w in windows.values()),
            "hours": n_days * 24,
        }
    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(f"wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
