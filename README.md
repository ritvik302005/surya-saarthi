# Surya Saarthi

*Steering every unit of sunshine to where it’s worth the most.*

> **This is the v2 project** (`Documents/surya-saarthi-v2`), a separate copy that started from the SIH `sih-improvements` branch on 27 Sep 2026. The SIH copy stays untouched. Where v2 is heading, and what's done, is in [docs/06-V2-Roadmap.md](docs/06-V2-Roadmap.md).

**Surya Saarthi** (सूर्य सारथी, "charioteer of the sun") is an agentic controller for a solar + battery + grid microgrid. Instead of falling back to the grid whenever solar/battery run low, or using static rule-based thresholds, this agent actually reasons about the current state (solar output, battery charge, demand) each cycle and decides how to allocate load — while hard safety limits stay in place to override it if it ever proposes something unsafe.

Built around SDG 7 (affordable and clean energy), targeting the kind of decentralized rooftop solar + battery setups you'd see under schemes like PM Surya Ghar or in a campus/community microgrid.

## How it works

Each cycle runs through a small LangGraph pipeline:

```
sense (+ forecast check) → allocate → safety → apply → report
```

- **sense** — pulls real solar irradiance for the site (via Open-Meteo, refreshed every 6 hours) plus an 8-hour solar forecast, and combines it with a simulated daily demand profile, battery state, and the Time-of-Day grid price. Actual solar varies around the forecast (passing clouds) by an amount set per weather scenario. It also **checks the forecast**: if this hour's actual solar differs from what last hour forecast for it by more than 1 kW, the hour is flagged (`replanned`, with `forecast_miss_kw`) and the agent is told to plan it cautiously.
- **allocate** — an LLM (`openai/gpt-oss-20b` via Groq, set in `config.LLM_MODEL`) looks at the current state and proposes how much load to draw from solar, battery, and grid, plus which flexible/deferrable loads to postpone.
- **safety** — enforces hard limits regardless of what the LLM proposed: battery never discharges below the reserve floor, charge/discharge never exceeds the rate ceiling, critical loads are never dropped.
- **apply** — applies the (possibly corrected) decision once: updates the battery state of charge and marks deferred jobs.
- **report** — logs the cycle: grid usage, cost savings vs. an all-grid baseline, CO₂ avoided (India grid factor 0.71 kg/kWh, CEA CO₂ Baseline Database v21.0), and any safety overrides that kicked in.

Every hour is decided and applied exactly once. (Earlier versions looped back from `apply` to `allocate` on a forecast miss, which applied the battery twice in that hour; `test_cycle_accounting.py` now guards against that.)

If the AI is unavailable, or the demo's AI budget is used up, the hour is decided by the **fixed rule** (solar, then battery above the reserve, then grid) — the same logic as the rule-based baseline — and marked as an AI-fallback hour.

Safety rules enforced after the LLM, every cycle: battery stays above the 20% reserve, charge/discharge stay under 5 kW, no more solar is used than is generated, every non-deferred load is powered, deferred jobs must run before their deadline, and surplus solar charges the battery. Solar still left over is exported to the grid (net metering).

### Time-of-Day tariff

Grid price follows India's 2023 Time-of-Day rules: solar hours (09–17) are at least 20% cheaper than normal, and the evening peak (18–22) is 10–20% costlier, set by each state; we assume 20%. Normal price is ₹8/kWh. The agent sees the next 8 hours of prices, so it saves battery for the peak and moves flexible loads out of it.

### Agent vs rule-based comparison

Every cycle, a fixed-rule controller (`backend/baseline.py`: solar, then battery, then grid, exports surplus, never defers) runs on the same solar and demand. The dashboard and `/simulate` summary show grid kWh for both, % less grid power, net cost (import minus export credit), renewable share, solar self-use %, export and wasted solar. `GET /history/csv` downloads per-hour results.

`python run_scenarios.py [days]` (from `backend`) runs all four weather scenarios with a fixed seed and writes `sample_results/<scenario>.json`. It lifts the demo's AI budget and warns if any hour fell back to the fixed rule.

### Repeatable runs (seeds)

Clouds and demand noise come from a seed plus the hour, so the same seed gives the same weather and demand. `/reset` and `/simulate` accept `"seed"`; without one, a random seed is picked. The seed is returned, stored on every hour and in the CSV. (The LLM's answers can still vary between runs.)

### Demo protection

| Setting (environment variable) | Default | What it does |
|---|---|---|
| `AI_HOURS_PER_DAY` | 150 | AI-decided hours for the whole demo per rolling 24 h (protects the Groq quota); after that, the fixed rule decides |
| `AI_HOURS_PER_SESSION_PER_DAY` | 48 | Same, per browser tab |
| `REQUESTS_PER_MINUTE_PER_SESSION` | 300 | Action requests per tab per minute; beyond it the API returns 429 with a message |
| `FRONTEND_ORIGINS` | `*` | Comma-separated sites allowed to call the API; set it to the deployed frontend URL in production |

`0` means no limit. Session ids come from the browser, so the per-session limits are a courtesy; the whole-demo AI budget is what protects the quota.

### Sessions

Each browser tab gets its own session (the frontend sends an `X-Session-Id` header), so several people can use the live demo at once. Requests without the header share a `default` session.

## Assumptions

| What | Value | Where |
|---|---|---|
| Location | Delhi (28.61 N, 77.21 E) | `config.LATITUDE/LONGITUDE` |
| Solar system | 10 kW | `config.SYSTEM_CAPACITY_KW` |
| Battery | 10 kWh, starts at 60%, 20% reserve, 5 kW max charge/discharge | `config.py`, `nodes/sensing.py` |
| Grid tariff | ₹8/kWh base; 09–17 ₹6.40 (−20%), 18–22 ₹9.60 (+20%; the peak surcharge is 10–20%, set by each state; we assume 20%) | `config.TOD_MULTIPLIERS` (2023 ToD rules) |
| Export credit | ₹3/kWh — **assumption**, varies by state/DISCOM | `config.EXPORT_CREDIT_RS_PER_KWH` |
| CO₂ factor | 0.71 kg/kWh (CEA CO₂ Baseline Database v21.0) | `config.GRID_EMISSION_FACTOR_KG_PER_KWH` |
| Essential load | Daily home/small-campus profile, 1.5–3.8 kW, ±10% | `nodes/sensing.py` |
| Flexible loads | Water pump 1.5 kW (06–09, due 10:00); EV charging 3 kW (18–22, due 06:00) | `nodes/sensing.py` |
| Demand data | Simulated (no smart meter yet) | — |
| Forecast error | Actual solar = forecast × noise (sunny 5%, normal 20%, cloudy 35%, monsoon 45%) | `config.WEATHER_SCENARIOS` |

## Project documents

- [PRD](docs/01-PRD.md) — problem, users, goals, MVP scope, success metrics
- [SRS](docs/02-SRS.md) — testable functional and non-functional requirements
- [Architecture](docs/03-Architecture.md) — components, data flow, API, deployment
- [UI/UX](docs/04-UI-UX.md) — screens, flows, states, design tokens
- [Development plan](docs/05-Development-Plan.md) — SIH milestones and Definition of Done
- [v2 roadmap](docs/06-V2-Roadmap.md) — the v2 positioning, phases and status
- [Third-party notices](THIRD_PARTY_NOTICES.md) — data, fonts, icons, packages and adapted components, with licences

## Privacy, credits and disclaimer

The site has a **Privacy & Disclaimer** page (`#/privacy`, linked from both footers): no cookies, no analytics, fonts served from the site (no Google requests), only a random session ID in the browser, and only simulated numbers sent to the AI. It is a simulation: not for controlling real equipment, and provided without warranty.

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Full credits are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and on the site at `#/credits`.

## Stack

- **Backend:** FastAPI + LangGraph + LangChain (Groq for LLM calls)
- **Frontend:** React + Vite + Tailwind, with a live dashboard, energy flow view, and history chart

## Running it locally

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # add your GROQ_API_KEY
uvicorn main:app --reload
```

Runs at `http://localhost:8000`.

Offline tests (no Groq calls, no network), from `backend`:

```bash
python test_cycle_accounting.py   # 48 h through the real pipeline: battery moves once per hour, loads powered, AI-off == baseline
python test_safety_rules.py       # safety checks, carry-over, report, baseline, forecast check, seeds
python test_allocation_parsing.py # LLM answer parsing, fixed-rule fallback, AI budget
python test_sessions.py           # per-tab sessions, seeds, AI budgets, rate limit
```

`test_graph.py`, `test_apply.py` and `test_forced_deviation.py` are live scripts that make real Groq calls.

Key endpoints:
- `POST /cycle` — advance one simulated hour
- `POST /simulate` — run a full batch (1–7 simulated days) under a chosen weather scenario in one call
- `GET /state`, `GET /history` — current and historical state
- `GET /history/csv`, `GET /history/download` — per-hour CSV / text log (`?session=` for links)
- `POST /reset` — reset the run, optionally switching weather scenario
- `GET /scenarios` — available weather scenarios (sunny / normal / cloudy / monsoon)

### Frontend

```bash
cd frontend
npm install
cp .env.example .env       # points VITE_API_URL at the backend
npm run dev
```

## Deployment note

The frontend (static Vite build) deploys cleanly to Vercel as-is. The backend keeps its state (current cycle, history) in memory between requests, which doesn't fit a stateless serverless function well — it's a better fit for a normal long-running host (Render, Railway, Fly.io, a VM, etc.) than Vercel's Python serverless runtime. Point `VITE_API_URL` at wherever the backend ends up.


