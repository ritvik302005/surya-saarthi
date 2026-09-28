# Surya Saarthi — Software Requirements Specification (SRS)

| | |
|---|---|
| Version | **v2** (27 Sep 2026) |
| Scope | Backend API (FastAPI + LangGraph + optimizer) and web frontend (React) in this repository |
| Related | [01-PRD](01-PRD.md) · [03-Architecture](03-Architecture.md) · [04-UI-UX](04-UI-UX.md) · [06-Roadmap](06-Roadmap.md) · [07-Benchmark-Results](07-Benchmark-Results.md) |

**Conventions.** Each requirement has an ID, a "shall" statement and a test. **Status**: `Done` (implemented; the named test exists in `backend/test_*.py` or is the manual check) or `Planned`. Units: kW, kWh, ₹, % SOC. One cycle = one simulated hour. All tunables are in `backend/config.py`.

Offline test files: `test_cycle_accounting.py`, `test_safety_rules.py`, `test_optimizer.py`, `test_features.py`, `test_allocation_parsing.py`, `test_sessions.py` (no Groq, no network).

---

## 1. Overview

The system simulates a site (solar, battery, grid, diesel genset, essential load, flexible jobs) hour by hour. Each hour a controller — the **optimizer** (default), the **AI** (LLM) or the **fixed rule** — proposes a dispatch; a deterministic plant model and safety layer (with a software BMS) corrects it; the result is applied, explained and reported, and compared with the fixed rule run on identical conditions. Operators can add power cuts, battery targets and grid limits in plain language. A dashboard and a benchmark on recorded weather show the results.

## 2. User roles

| Role | Permissions |
|---|---|
| **Viewer** (anonymous) | One session per browser tab: run hours/simulations, switch controller, add/clear constraints, inject BMS faults (test), run what-ifs, download history. Cannot see other sessions. |
| **Script user** | Same, on the shared `default` session (curl, tests, `run_scenarios.py`). |
| **Site controller** (future device) | `GET /plan`; needs `X-Api-Key` when `DEVICE_API_KEY` is set. |
| **Operator** | Environment variables and `config.py`; server logs. No admin UI. |

No user accounts. Isolation is by session id.

## 3. Functional requirements

### 3.1 Sensing

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-S1 | Live mode shall fetch hourly shortwave irradiance and air temperature for the site from Open-Meteo (8 days) and cache them. | `fetch_hourly_irradiance()` length ≥ 192 | Done |
| FR-S2 | If the weather API fails, a clear-sky curve and 30 °C shall be used and the run continues. | Offline tests use it | Done |
| FR-S3 | A cache older than 6 h shall be re-fetched when a run starts, never mid-run. | Code review | Done |
| FR-S4 | Solar AC output = capacity × GHI/1000 × (1 − 14% losses) × (1 − 0.4%/°C above 25 °C cell temperature, NOCT model) × 96% inverter, capped at the 10 kW inverter. | `test_safety_rules.py` 10b (1000 W/m², 25 °C → 7.22 kW; never > 10 kW) | Done |
| FR-S5 | Live mode: forecast = weather × scenario multiplier; actual = forecast × N(1, variability) clipped to [0.1, 1.25], keyed on (seed, hour). | 9c (same seed → same values) | Done |
| FR-S6 | Recorded mode (`weather_source`): actual and day-ahead forecast come from `data/weather_delhi.json`. | `benchmark.py` | Done |
| FR-S7 | A 23-hour solar forecast shall be provided (`solar_forecast_next_hours`); the LLM prompt uses the first 8. | Optimizer tests | Done |
| FR-S8 | Forecast correction (optional, `FORECAST_CORRECTION`, default off) blends the recent actual/forecast ratio into the next hours. | `benchmark.py` MAE comparison | Done (off: measured not to help) |
| FR-S9 | Essential load = daily profile × U(0.9, 1.1) (+ `extra_load_kw` in what-ifs). Pump jobs (1.5 kW, due 10:00) arrive 06–09; EV jobs (3 kW, due 06:00) 18–22. | Case 8 | Done |
| FR-S10 | Deferred jobs carry forward; a job with ≤ 1 h to its deadline is `must_run`. | Case 8 | Done |
| FR-S11 | Price = ₹8 × 0.8 (09–16), × 1.2 (18–21, or `peak_multiplier`), else × 1.0; `price_band` labels it. | Code + UI | Done |
| FR-S12 | `grid_available` is false during any `[start, end)` outage window. | `test_features.py` 3 | Done |
| FR-S13 | The BMS publishes limits for this hour from SOC, health and temperature (FR-B1–B4); battery capacity = 10 kWh × health. | Case 13 | Done |
| FR-S14 | Forecast check: `forecast_miss_kw` = actual − last hour's forecast for this hour; `replanned` when \|miss\| > 1 kW, before deciding. | 9b; `test_cycle_accounting.py` | Done |

### 3.2 Controllers

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-D1 | The decide step shall use the session's controller: `optimizer` (default), `ai` or `fixed`; `POST /controller` switches it; unknown names are rejected. | `test_sessions.py` | Done |
| FR-D2 | **Fixed rule**: solar first, then battery down to the reserve within the BMS limit, then grid; all jobs run now. In a power cut: essentials and due jobs only, solar → battery → genset. | Case 10, 12 | Done |
| FR-D3 | **Optimizer**: a 24-hour MILP minimising grid cost − export credit + battery wear + diesel + penalties (unserved essential ₹1,000/kWh, missed job, missed target) − value of energy left at the end; applies the first hour. | `test_optimizer.py` | Done |
| FR-D4 | The optimizer shall mirror the plant: solar serves load first; charging only from sun or genset; genset ≥ 30% of rating when on; one-hour jobs once before their deadline, not during cuts except their last hour; SOC within reserve–100% with efficiency; BMS limits; DR import caps; operator SOC targets. | `test_optimizer.py` 1–7 | Done |
| FR-D5 | The plant shall apply the optimizer's battery decision unchanged (± 0.1 kW) and never override its plans. | `test_cycle_accounting.py` (0 overrides, battery match) | Done |
| FR-D6 | If the optimizer finds no plan, the fixed rule decides with an "Optimizer fallback" alert. | Code | Done |
| FR-A1 | **AI**: the prompt shall include scenario, hour, solar now + 8 h forecast, battery, BMS limits, load, jobs, prices (now + 8 h), grid status, scheduled cuts, operator targets. | `test_apply.py` (live) | Done |
| FR-A2 | The LLM answer uses a strict JSON schema (`solar_used_kw`, `battery_used_kw`, `grid_used_kw`, `defer_loads[]`, `reasoning`) and is validated (numbers finite, known jobs, non-empty reasoning); fenced JSON is extracted. | `test_allocation_parsing.py` | Done |
| FR-A3 | 429 / malformed / 503 / timeout are retried up to `LLM_MAX_ATTEMPTS` with the delay Groq states or back-off; the daily-token limit is not retried. | Code | Done |
| FR-A4 | If no valid answer, or the AI budget is used up, the fixed rule decides (`ai_fallback`, alert "AI fallback: …"); when the budget is used up the LLM is not called. | `test_allocation_parsing.py`; AI-off == baseline | Done |

### 3.3 Safety and plant model (every controller, in this order)

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-SF0 | `must_run` jobs can't be deferred (alert); in a power cut, other flexible jobs are deferred (alert). | Cases 5, 12 | Done |
| FR-SF1 | Solar serves load first, never more than generated (alert if the proposal claimed more). | Case 1 | Done |
| FR-SF2 | Discharge ≤ min(energy above the 20% reserve × discharge efficiency, BMS limit), and never more than the remaining load (alert if capped). | Case 2 | Done |
| FR-SF3 | A proposed genset runs at ≥ 30% of its rating and ≤ its rating. | Case 12 | Done |
| FR-SF4 | Grid available: the rest comes from the grid (alert if the proposal left load unpowered; unused import trimmed). Power cut: more battery → genset → unserved (alerts). | Cases 3, 7, 12 | Done |
| FR-SF5 | Spare genset output serves load before the battery does, then charges it. | Case 12 (`tiny`) | Done |
| FR-SF6 | Surplus sun (then spare genset) charges the battery up to min(room to 100% ÷ charge efficiency, BMS limit); never from the grid. | Cases 6, 7b | Done |
| FR-SF7 | Leftover sun is exported up to the export limit (grid available) or curtailed (power cut). | Case 7c | Done |
| FR-SF8 | BMS alarms are added as "BMS: …" alerts; differences ≤ 0.01 kW trigger nothing; zero battery power is `0.0`. | Case 13 | Done |

### 3.4 Battery management (software BMS)

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-B1 | Charging tapers linearly to 0 between 90% and 100% SOC; discharge tapers to 0 between 25% and the reserve. | Case 13 | Done |
| FR-B2 | Battery temperature ≈ air + 3 °C; limits halved at ≥ 45 °C; battery disconnected at ≥ 55 °C; no charging below 0 °C. | Case 13 | Done |
| FR-B3 | Health < 80% raises an end-of-life alarm. | Code | Done |
| FR-B4 | Faults `overtemp` and `sensor_lost` can be injected (`POST /bms/fault`) and isolate the battery. | `test_features.py` 4 | Done |

### 3.5 Apply, report, explain

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-R1 | Battery SOC changes once per hour: discharge removes kW ÷ discharge efficiency; charging adds kW × charge efficiency (92% round trip). | `test_cycle_accounting.py`; case 10b | Done |
| FR-R2 | Health falls with energy taken out, reaching 80% after 4,000 × 80% full cycles. | Code | Done |
| FR-R3 | Deferred jobs are marked `deferred`. | Case 8 | Done |
| FR-R4 | Report: served load, import cost, export credit, battery wear, diesel litres and cost, unserved kW, grid availability, net cost (import − credit + wear + diesel), savings vs a site with no solar/battery (grid, or diesel in a cut), CO₂ (grid and diesel), solar accounting, alerts, forecast-miss fields. | Cases 9, 11 | Done |
| FR-R5 | Optimizer explanations in English and Hindi are generated from the plan's facts (next cut, battery at the cut, next battery use and its price, moved jobs, forecast miss) and rewritten after safety from the applied decision. | `test_optimizer.py` 8 | Done |

### 3.6 Comparison and benchmark

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-C1 | Each hour the fixed rule runs through the same graph with the same inputs (seed, scenario, cuts, targets, DR, fault) and its own battery and job queue. | AI-off == baseline in 4 scenarios | Done |
| FR-C2 | The comparison reports grid kWh, net cost, savings, renewable share, self-use, export, waste, power-cut hours, diesel, unserved kWh, battery wear, AI-fallback and override hours for both. | `/state` → `comparison` | Done |
| FR-C3 | `benchmark.py` runs fixed rule, optimizer, optimizer with forecast correction and perfect-forecast optimizer on four recorded weeks, grid normal and with a daily 19–22 cut; `--ai-days N` adds the LLM on one season; writes `sample_results/benchmark.json` and the landing summary. Costs are adjusted for battery energy left at the end. | Run | Done |

### 3.7 Operator notes, constraints, what-if, device plan

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-N1 | `POST /note/interpret` reads a note (≤ 300 chars) into actions — outage, SOC target, DR cap — via the LLM (strict schema) when the AI budget allows, else a rule-based parser (Hindi/Hinglish/English time phrases). It changes nothing. | `test_features.py` 1–2 | Done |
| FR-N2 | Actions are validated: windows start within 48 h and last 1–12 h; targets between the reserve and 100% within 48 h; DR caps 0–20 kW. Invalid → 400. | `test_features.py` 2–3 | Done |
| FR-N3 | `POST /note/apply` adds validated actions to the session; `GET /constraints` lists them; `POST /constraints/clear` removes one kind or all. | `test_features.py` 3–4 | Done |
| FR-N4 | `POST /reset` with `keep_constraints` carries constraints into the new run at the same time of day; a plain reset clears them. | Browser check | Done |
| FR-W1 | `POST /whatif` replays the next 24 h from the session's current moment (session untouched, no AI calls) as optimizer-now, optimizer-with-changes and fixed-rule-with-changes; inputs are validated; totals include cost adjusted for battery energy left. | `test_features.py` 5 | Done |
| FR-P1 | `GET /plan` returns the optimizer's 24 h schedule; requires `X-Api-Key` when `DEVICE_API_KEY` is set (401 otherwise); signed with HMAC-SHA256 over the sorted-key JSON when `PLAN_SIGNING_KEY` is set. | `test_features.py` 6 | Done |

### 3.8 Sessions and API

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-API1 | Session id from `X-Session-Id` or `?session=`; sanitised `[A-Za-z0-9_-]`, ≤ 64 chars; empty → `default`. At most 100 sessions (LRU); one lock per session. | `test_sessions.py` | Done |
| FR-API2 | Seeds: `/reset` and `/simulate` accept `seed`; otherwise random; stored per hour and in the CSV. | `test_sessions.py` | Done |
| FR-API3 | Endpoints as in [03-Architecture §5](03-Architecture.md#5-api). | Tests | Done |
| FR-API4 | Invalid `/simulate` or `/reset` scenario, days or controller, and an unknown `/controller`, return 400; empty CSV/log downloads return 404; the body stays `{"error": …}`. | `test_sessions.py` | Done |

### 3.9 Frontend

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-UI1 | Per-tab session id in `sessionStorage`; state, chart, totals, scenario and controller restored on load. | Browser | Done |
| FR-UI2 | Controller switch (Optimizer / AI / Fixed rule) and language switch (English / हिंदी); Hindi shown when available. | Browser check | Done |
| FR-UI3 | 3D energy scene: solar, battery (level), tower (dark in a cut), genset (running effects), house (windows dim if unserved); particle flows scale with kW; labels with values; screen-reader summary. | Browser check (5 labels, summary) | Done |
| FR-UI4 | Without WebGL the flat diagram is shown; with reduced motion the 3D scene is still; nothing crashes the page. | Browser checks | Done |
| FR-UI5 | Operator panel: note → interpretation (with source) → Apply/Cancel; active constraints with Clear; BMS fault test buttons. | Browser check | Done |
| FR-UI6 | What-if panel: sun, power cut, battery health, peak price, extra load, DR; results table (3 runs × 5 metrics) and battery chart. | Browser check | Done |
| FR-UI7 | Situation panel shows "Power cut" and genset kW in cuts; comparison card shows power-cut hours, diesel, unserved, battery wear. | Browser check | Done |
| FR-UI8 | Landing results strip and FAQ numbers come from `results-summary.json`. | Browser check | Done |
| FR-UI9 | Server error messages (e.g. rate limit) are shown to the user. | Browser check | Done |

## 4. Business rules

| ID | Rule |
|---|---|
| BR1 | Safety rules and BMS limits always win, whoever decides. |
| BR2 | Load is served by solar first; the battery charges only from sun or genset, never the grid. |
| BR3 | In a power cut: no grid, no export; essentials and due jobs only; battery, then genset, then (only if impossible) unserved. |
| BR4 | Export only after load and battery charging are satisfied. |
| BR5 | A flexible job must run by its deadline. |
| BR6 | Savings are stated against baselines with the same inputs: the fixed rule (comparison, benchmark) and a site with no solar/battery (per-hour report). |
| BR7 | Operator notes never change anything until confirmed; the LLM never commands a device. |
| BR8 | Simulated inputs (demand, illustrative cuts) and placeholder prices are labelled as such. |

## 5. Data

### 5.1 Session state (`GridState`)
See `backend/state.py` (every field is declared and commented there): hour, scenario, controller, weather source, solar and temperature, battery SOC/health/capacity/BMS, load and jobs, price, grid availability, outages, SOC targets, DR events, what-if fields, forecasts and forecast-check fields, seed, decision, plan, reasoning (EN/HI), AI flags, alerts, report.

### 5.2 History entry (per hour)
`cycle, sim_hour, scenario, timestamp, controller, grid_available, solar_kw, battery_kw, grid_kw, export_kw, genset_kw, diesel_l, unserved_kw, load_kw, deferred_loads, battery_soc_pct, battery_soh_pct, battery_wear_rs, reasoning, alerts, replanned, forecast_miss_kw, seed, savings_rs, carbon_avoided_kg, grid_price_rs, agent_cost_rs, solar_available_kw, solar_self_used_kw, solar_curtailed_kw, rule_grid_kw, rule_battery_kw, rule_cost_rs, rule_export_kw, rule_diesel_l, rule_unserved_kw, rule_battery_wear_rs, rule_solar_self_used_kw, rule_battery_soc_pct, ai_fallback`.

### 5.3 Persistence
In memory only (sessions, history, constraints). Server log in `backend/logs/`. Recorded weather and benchmark results in git. No personal data is collected; operator-note text is sent to Groq to be understood and not stored.

## 6. Validation summary

| Input | Rule | On failure |
|---|---|---|
| `scenario` | Key of `WEATHER_SCENARIOS` | 400 |
| `days` | 1–7 | Error body |
| `controller` | optimizer / ai / fixed | Error body |
| Note text / actions | FR-N1, FR-N2 | 400 |
| What-if changes | sun 0–1.5, health 50–100%, peak ×1–2, extra 0–5 kW, windows 1–12 h, DR cap 0–20 kW | 400 |
| BMS fault | overtemp / sensor_lost / null | 400 |
| LLM output | FR-A2 | Fixed-rule fallback |

## 7. Authentication and authorization

- **AUTH1** No login; public demo. *(Done — deliberate.)*
- **AUTH2** Sessions only accessible with their unguessable id. *(Done)*
- **AUTH3** `GROQ_API_KEY` server-side only. *(Done)*
- **AUTH4** `/plan` key-protected and signed when configured. *(Done)*
- **AUTH5** Operator login on write endpoints before any real equipment is controlled. *(Planned)*

## 8. Error handling

| Situation | Behaviour | Status |
|---|---|---|
| Weather API down | Clear-sky fallback | Done |
| LLM errors / key missing / budget used | Retry, then fixed-rule fallback, labelled | Done |
| Optimizer finds no plan | Fixed-rule fallback, labelled | Done |
| Note/what-if invalid | 400 + message shown in the UI | Done |
| Too many requests | 429 + message shown | Done |
| No WebGL / 3D scene fails | Flat diagram; landing background skipped | Done |
| Backend unreachable | "Can't reach the backend at …" | Done |

## 9. Edge cases

1. Night: no solar, no export, no charging from sun.
2. Battery at the reserve: no discharge; full: no charging (taper), surplus exported.
3. First hour: no previous forecast → not flagged.
4. Power cut with little battery: genset at ≥ minimum load; its spare output charges the battery.
5. Power cut bigger than battery + genset: remaining essential load reported unserved.
6. Deadline wraps midnight (EV 22:00 → 06:00); a job due during a cut runs in its last hour.
7. AI defers a must-run job → removed; names an unknown job → answer rejected → fallback.
8. BMS overtemp/sensor fault → battery isolated; the optimizer plans with zero battery.
9. 101st session → oldest evicted.
10. Simulate with constraints → carried to day 1 at the same time of day.

## 10. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-S1 | No secrets in the repo; `.env` git-ignored. | Done |
| NFR-S2 | Session ids sanitised; no user input reaches file paths or a shell. | Done |
| NFR-S3 | CORS restricted via `FRONTEND_ORIGINS` in production. | Done (configure on deploy) |
| NFR-S4 | Dependencies pinned (`requirements.txt` incl. scipy/numpy, `package-lock.json`). | Done |
| NFR-S5 | AI budget per rolling 24 h (demo 150, tab 48) and per-tab request limit (300/min). | Done |
| NFR-PR1 | No cookies, analytics or third-party browser requests; fonts self-hosted. | Done |
| NFR-PR2 | Groq receives simulated numbers (AI mode) and operator-note text only; Open-Meteo the site coordinates. Stated on the Privacy page. | Done |
| NFR-PR3 | Open-Meteo attribution in both footers; credits and `THIRD_PARTY_NOTICES.md`; licence headers kept in the built JS. | Done |
| NFR-PF1 | Optimizer hour (with baseline) ≈ 40 ms; a 7-day benchmark week per controller ≈ 4 s. | Done |
| NFR-PF2 | Heavy visuals lazy-loaded (3D scene ~13 kB + three.js shared). | Done |
| NFR-U1 | Usable at 390 px without horizontal scroll. | Done |
| NFR-U2 | Respects `prefers-reduced-motion`. | Done |
| NFR-U3 | Works without WebGL. | Done |

## 11. Acceptance criteria

1. All `Done` requirements pass their tests; the six offline test files pass with no network.
2. The benchmark shows 0 safety overrides of optimizer plans and 0 unserved essential load.
3. `npm run build` succeeds; the browser checks pass on desktop and 390 px.
4. `Planned` items (AUTH5) are implemented or explicitly deferred in the roadmap.
