# Surya Saarthi v2 — project memory (read this first in a new chat)

Last updated: 27 Sep 2026. Keep this file current at the end of every working session.

## What this is
- **Surya Saarthi** ("charioteer of the sun"), team **BOOMERS**, Smart India Hackathon 2026, PS **SIH26200** (AICTE, Renewable/Sustainable Energy, Software).
- v2 pitch: *keeps essential power on through power cuts at the lowest cost and least battery wear. An optimizer decides, hard safety rules guard, and an AI understands the operator and explains every decision in plain English or Hindi.*
- Users: homes with solar + inverter battery, schools/clinics/small businesses with a diesel genset, village/farm mini-grids.

## Two repos — never mix them
| Repo | Path | Branch | Status |
|---|---|---|---|
| **v2 (this one)** | `C:\Users\RITVIK\Documents\surya-saarthi-v2` | `main` | All new work. **No git remote**; nothing pushed. Ask before creating a GitHub repo or pushing. |
| SIH version (v1) | `C:\Users\RITVIK\Documents\microgrid-agent-sih` | `sih-improvements` | Pushed to github.com/ritvik302005/microgrid-agent; **do not modify** without asking. Not merged to `main`. |

Live site (still v1, deploys from `main` of the GitHub repo): frontend https://microgrid-agent.vercel.app, backend https://microgrid-agent.onrender.com.

## v2 commits (newest first)
- `3a74778` 3D energy scene; landing no longer blank without WebGL
- `9558ba0` benchmark on recorded weather, operator notes, what-if, DR, signed device plan, v2 dashboard
- `4af9347` physics, power cuts + genset, software BMS, 24 h optimizer, EN/HI explanations
- `7c64d02` Phase 0: replan double-apply bug fixed, seeds, fixed-rule fallback, demo protection
- (plus the doc/memory commit that added this file)

## Architecture in one breath
LangGraph pipeline per simulated hour: `sense` (weather live/recorded, 23 h forecast, demand + jobs, BMS limits, power cuts, price, forecast check) → `decide` (`optimizer` default = 24 h MILP via scipy/HiGHS, MPC; `ai` = Groq LLM; `fixed` = fixed rule) → `safety` (plant model, same for all controllers) → `apply` (SOC with 92% round trip, health) → `report` (+ EN/HI explanation written after safety). The fixed-rule baseline runs through the same graph each hour. Key files: `backend/{config,physics,bms,optimizer,explain,notes,whatif,benchmark,main}.py`, `backend/nodes/*`, `frontend/src/{Dashboard,EnergyScene3D,EnergyView,OperatorPanel,WhatIfPanel,Landing,webgl}.jsx`. Docs: `docs/01–07`, README.

## Results (simulated; `docs/07-Benchmark-Results.md`)
4 recorded Delhi weeks (Jan/May/Jul/Sep 2026, ERA5 actual + day-ahead forecast), 10 kW solar / 10 kWh battery / 5 kW genset:
- Optimizer vs fixed rule: **−10.0% cost** grid normal; **−26.0%** with illustrative daily 19–22 cut; diesel **36.7 L vs 97.5 L**; **0** safety overrides in 1,344 h; 0 unserved.
- Perfect forecast ≈ same (forecast not the bottleneck). Forecast correction measured, left off.
- AI 1-day sample (48 Groq calls): fixed ₹417 / AI ₹300 (9 override hours) / optimizer ₹269.
- **Placeholders** in `config.py` to replace with real quotes before quoting ₹: battery ₹12,000/kWh, 4,000 cycles, diesel ₹90/L, 2.8 kWh/L, export ₹3/kWh.

## How to run / test (Windows)
- Python: use `C:\Python314\python.exe` (plain `python` hits the Store stub). No venv.
- Backend: `cd backend; python -m uvicorn main:app --port 8000` (key in `backend/.env`, git-ignored). Frontend: `cd frontend; npm run build; npx vite preview --port 4173` (or `npm run dev`).
- Offline tests (no quota): `GROQ_API_KEY= python <file>` for `test_cycle_accounting, test_safety_rules, test_optimizer, test_features, test_allocation_parsing, test_sessions` — all pass.
- Benchmark: `python benchmark.py` (~2 min); `--ai-days N` uses Groq.
- Browser checks (Playwright via installed Chrome) need WebGL flags: `--use-gl=angle --use-angle=swiftshader-webgl --enable-unsafe-swiftshader --ignore-gpu-blocklist`. The landing page doesn't create the session id; the dashboard (api.js) does.
- Console printing Hindi on Windows: set `PYTHONIOENCODING=utf-8`.

## Groq quota
Free tier ~8k tokens/min and ~200k tokens/day (~1k tokens per AI hour). Optimizer mode, what-if and the benchmark (without `--ai-days`) use **no** quota. Demo limits: `AI_HOURS_PER_DAY` 150, per tab 48.

## Open decisions / not done
1. GitHub for v2 (new repo vs branch) and deploy (Render `PYTHON_VERSION=3.12`, `FRONTEND_ORIGINS`, AI budget).
2. Next SIH deadline; deck results slide + submission text still to write.
3. Real prices → rerun benchmark.
4. Not built: ESP32 testbed + digital-twin sync, ESMI outage data, cell-level BMS/Kalman/BLAST-Lite, LLM-phrased explanations + checker, logins on control endpoints, 400/404 codes (FR-API4), multi-site, attack detection, stakeholder interviews.
5. The no-WebGL blank-landing bug is fixed in v2 but **still present in the SIH repo/live site** — ask before fixing there.

## Working style the user expects
- Plain, non-technical wording; honest claims only; never quote numbers not produced by a run on current code; label simulated/illustrative/placeholder values.
- Tariff wording: "solar hours at least 20% cheaper; peak 10–20% costlier, set by each state; we assume 20%".
- User often says "tell me first" — propose, then implement after approval. Commit locally; don't push without asking.
