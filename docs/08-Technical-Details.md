# Technical details

How Surya Saarthi works inside, the settings it reads, and the assumptions behind the numbers. For a short overview, see the [README](../README.md).

## How it works

Each simulated hour runs through a LangGraph pipeline:

```
sense (+ forecast check) → decide (optimizer | AI | fixed rule) → safety & BMS limits → apply → explain & report
```

- **sense** — sunlight and air temperature for the site (Open-Meteo live forecast in the demo; recorded weather in the benchmark), a 24-hour solar forecast, the demand profile and flexible jobs, the battery management system's live limits, scheduled power cuts and the time-of-day price. **Forecast check:** if this hour's actual solar differs from what last hour forecast for it by more than 1 kW, the hour is flagged (`replanned`, `forecast_miss_kw`) and planned cautiously.
- **decide** — one of three controllers ([nodes/decide.py](../backend/nodes/decide.py)):
  - **optimizer** (default): a 24-hour mixed-integer plan ([backend/optimizer.py](../backend/optimizer.py), SciPy + HiGHS), re-made every hour (model predictive control), first hour applied. It follows the plant's own rules, so its plans pass the safety check unchanged.
  - **ai**: the LLM (`openai/gpt-oss-20b` via Groq) proposes the split; kept for comparison. If the AI is unavailable or the demo's AI budget is used up, the fixed rule decides that hour (an AI-fallback hour).
  - **fixed**: solar, then battery above the reserve, then grid (genset in a cut) — what a typical controller does, and the comparison baseline.
- **safety** — the plant model and hard rules, the same for every controller ([nodes/safety.py](../backend/nodes/safety.py)): solar serves load first; battery within the 20% reserve and the BMS's live limits; charging only from sun or genset, never the grid; every non-deferred load powered; in a power cut no grid or export, flexible jobs wait, battery then genset (with its minimum load) then, only if impossible, unserved essential load; leftover sun is exported.
- **apply** — the battery updates once, with charge/discharge losses and wear (state of health).
- **explain & report** — cost (import − export credit + battery wear + diesel), CO₂ (grid and diesel), and for the optimizer a plain-language explanation in **English and Hindi**, written from the plan's own numbers after the safety check ([backend/explain.py](../backend/explain.py)).

The fixed-rule baseline runs through the **same** pipeline every hour (same seed, weather, demand and power cuts, its own battery), so the comparison is fair by construction; with the AI off, the two match exactly (`tests/test_cycle_accounting.py`).

### Operator notes (the AI's language job)

Type a note in Hindi, Hinglish or English — *"kal shaam 7 se 10 bijli jayegi"*, *"battery full by 6 pm"*, *"DISCOM: grid max 2 kW 6-8 pm"*. The LLM reads it into a strict schema (a rule-based parser handles common phrasings if the AI is unavailable); the result is validated and **shown for confirmation before anything changes**. Confirmed notes become power-cut windows, battery targets or demand-response limits for the optimizer ([backend/notes.py](../backend/notes.py)). The LLM never controls a device.

### Battery physics and BMS

Round-trip efficiency 92%, wear cost per kWh taken out (replacement cost ÷ lifetime throughput), state of health falling with use ([backend/physics.py](../backend/physics.py)). A software BMS ([backend/bms.py](../backend/bms.py)) publishes live limits: charging tapers above 90%, discharge tapers near the reserve, limits halve above 45 °C and cut off at 55 °C, no charging below 0 °C (LFP); faults (`overtemp`, `sensor_lost`) can be injected to show the system backing off. Pack-level only; no cell-level model or Kalman filter.

### Solar physics

PVWatts-style: 14% system losses, −0.4%/°C above 25 °C cell temperature (NOCT model), 96% inverter, output capped at the 10 kW inverter. Panel tilt is ignored.

### What-if

`POST /whatif` replays the next 24 hours from the session's current moment with changed conditions — less sun, a power cut, battery health, peak tariff, extra load, a DISCOM grid limit — for the optimizer (now vs what-if) and the fixed rule, on the same seed, with no AI calls ([backend/whatif.py](../backend/whatif.py)). Costs are compared with the change in battery charge over the 24 hours counted, the same rule as the benchmark.

### 24-hour plan for a site controller

`GET /plan` returns the optimizer's schedule for the next 24 hours, for an edge device to cache and follow (with its own safety rules) if the connection drops; stale or unsigned → fall back to the fixed rule. With `PLAN_SIGNING_KEY` set it is signed (HMAC-SHA256); with `DEVICE_API_KEY` set, callers must send `X-Api-Key`. No real device is connected yet.

### Benchmark

`python benchmark.py [--ai-days N]` (from `backend`) runs the fixed rule, the optimizer (real day-ahead forecast, with/without forecast correction) and the optimizer with perfect forecast on four recorded weeks of Delhi weather (`data/weather_delhi.json`, fetched by `data/fetch_weather.py`), grid normal and with an illustrative daily 19–22 power cut; `--ai-days N` adds the LLM on N days of one season (uses Groq quota). Writes `sample_results/benchmark.json` and the landing page's results strip. `run_scenarios.py` (from v1) still runs the four synthetic weather scenarios.

### Time-of-Day tariff

Solar hours (09–17) are at least 20% cheaper than normal, and the evening peak (18–22) is 10–20% costlier, set by each state; we assume 20%. Normal price is ₹8/kWh.

### Repeatable runs, sessions and demo protection

- Clouds and demand noise come from a seed plus the hour; `/reset` and `/simulate` accept `"seed"`; the seed is stored on every hour and in the CSV. (The LLM's answers can still vary.)
- Each browser tab gets its own session (`X-Session-Id`).

| Setting (environment variable) | Default | What it does |
|---|---|---|
| `AI_HOURS_PER_DAY` | 150 | AI-decided hours (and AI note readings) for the whole demo per rolling 24 h; after that, the fixed rule decides / the rule parser reads notes |
| `AI_HOURS_PER_SESSION_PER_DAY` | 48 | Same, per browser tab |
| `REQUESTS_PER_MINUTE_PER_SESSION` | 300 | Action requests per tab per minute; beyond it the API returns 429 with a message |
| `FRONTEND_ORIGINS` | `*` | Comma-separated sites allowed to call the API; set it to the deployed frontend URL in production |
| `DEVICE_API_KEY` / `PLAN_SIGNING_KEY` | unset | Protect and sign `/plan` |

`0` means no limit. Session ids come from the browser, so the per-session limits are a courtesy; the whole-demo AI budget is what protects the quota.

## Assumptions

| What | Value | Where |
|---|---|---|
| Location | Delhi (28.61 N, 77.21 E) | `config.LATITUDE/LONGITUDE` |
| Solar system | 10 kW, PVWatts-style losses and heat derating, 10 kW inverter | `config.py` (solar physics) |
| Battery | 10 kWh, starts at 60%, 20% reserve, 5 kW max charge/discharge, 92% round trip (**assumption**) | `config.py` |
| Battery wear | Rs 12,000/kWh replacement (**placeholder**) ÷ (4,000 cycles × 80% depth) = Rs 3.75 per kWh taken out | `config.BATTERY_*` |
| Diesel genset | 5 kW, minimum load 30%, Rs 90/L (**assumption**), 2.8 kWh/L (**assumption**) → Rs 32/kWh; 2.68 kg CO₂/L | `config.GENSET_*` |
| Grid tariff | ₹8/kWh base; 09–17 ₹6.40 (−20%), 18–22 ₹9.60 (+20%; the peak surcharge is 10–20%, set by each state; we assume 20%) | `config.TOD_MULTIPLIERS` (2023 ToD rules) |
| Export credit | ₹3/kWh — **assumption**, varies by state/DISCOM | `config.EXPORT_CREDIT_RS_PER_KWH` |
| CO₂ factor | 0.71 kg/kWh (CEA CO₂ Baseline Database v21.0) | `config.GRID_EMISSION_FACTOR_KG_PER_KWH` |
| Essential load | Daily home/small-campus profile, 1.5–3.8 kW, ±10% | `nodes/sensing.py` |
| Flexible loads | Water pump 1.5 kW (06–09, due 10:00); EV charging 3 kW (18–22, due 06:00) | `nodes/sensing.py` |
| Demand data | Simulated (no smart meter yet) | — |
| Weather (demo) | Live forecast × scenario multiplier; actual = forecast × noise (sunny 5%, normal 20%, cloudy 35%, monsoon 45%) | `config.WEATHER_SCENARIOS` |
| Weather (benchmark) | Recorded actual (ERA5) + day-ahead forecasts actually issued, four weeks in 2026 | `data/weather_delhi.json` |
| Power cuts (benchmark) | Illustrative: 19:00–22:00 daily, known in advance | `benchmark.py` |
| Baseline for "savings" | A site with no solar or battery: grid, or diesel in a power cut | `nodes/report.py` |

## Stack

- **Backend:** FastAPI + LangGraph + SciPy (HiGHS MILP solver) + LangChain/Groq for the LLM
- **Frontend:** React + Vite + Tailwind: live dashboard, 3D energy scene, operator notes, what-if, comparison, history

The dashboard's energy view is a small 3D site built with three.js ([frontend/src/EnergyScene3D.jsx](../frontend/src/EnergyScene3D.jsx)): solar array under a sun that follows the output, battery cabinet showing its charge, transmission tower (dark in a power cut), diesel genset (shakes and smokes when running) and the house (windows dim if load goes unserved), with glowing particles flowing faster and denser with more kW. Numbers are HTML labels pinned to each model. Without WebGL it falls back to the flat diagram ([EnergyFlow.jsx](../frontend/src/EnergyFlow.jsx)); with reduced motion it renders a still scene; screen readers get a one-sentence summary.

## API endpoints

- `POST /cycle` — one simulated hour; `POST /simulate` — 1–7 days in one call
- `POST /reset` (`scenario`, `seed`, `controller`, `keep_constraints`), `POST /controller` (`optimizer` | `ai` | `fixed`)
- `POST /note/interpret`, `POST /note/apply`, `GET /constraints`, `POST /constraints/clear`, `POST /bms/fault`
- `POST /whatif`, `GET /plan`
- `GET /state`, `GET /history`, `GET /history/csv`, `GET /history/download`, `GET /scenarios`, `GET /health`
