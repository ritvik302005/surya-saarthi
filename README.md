# Microgrid Agent

An agentic controller for a solar + battery + grid microgrid. Instead of falling back to the grid whenever solar/battery run low, or using static rule-based thresholds, this agent actually reasons about the current state (solar output, battery charge, demand) each cycle and decides how to allocate load — while hard safety limits stay in place to override it if it ever proposes something unsafe.

Built around SDG 7 (affordable and clean energy), targeting the kind of decentralized rooftop solar + battery setups you'd see under schemes like PM Surya Ghar or in a campus/community microgrid.

## How it works

Each cycle runs through a small LangGraph pipeline:

```
sense → allocate → safety → apply → report
           ↑                  |
           └── replan ────────┘
```

- **sense** — pulls real solar irradiance for the site (via Open-Meteo) and combines it with a simulated demand profile, battery state, and grid price for the current cycle.
- **allocate** — an LLM (`openai/gpt-oss-20b` via Groq, set in `config.LLM_MODEL`) looks at the current state and proposes how much load to draw from solar, battery, and grid, plus which flexible/deferrable loads to postpone.
- **safety** — enforces hard limits regardless of what the LLM proposed: battery never discharges below the reserve floor, charge/discharge never exceeds the rate ceiling, critical loads are never dropped.
- **apply** — applies the (possibly corrected) decision, updates battery state of charge, and checks whether real conditions deviated enough from the forecast to warrant a replan.
- **report** — logs the cycle: grid usage, cost savings vs. an all-grid baseline, CO₂ avoided (India grid factor 0.71 kg/kWh, CEA CO₂ Baseline Database v21.0), and any safety overrides that kicked in.

If actual conditions drift too far from what was planned, the loop jumps back to `allocate` and replans before finishing the cycle.

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

Key endpoints:
- `POST /cycle` — advance one simulated hour
- `POST /simulate` — run a full batch (1–7 simulated days) under a chosen weather scenario in one call
- `GET /state`, `GET /history` — current and historical state
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


