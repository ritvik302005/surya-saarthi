# Surya Saarthi — Software Requirements Specification (SRS)

| | |
|---|---|
| Version | 1.0 (MVP) |
| Scope | Backend API (FastAPI + LangGraph agent) and web frontend (React) in this repository |
| Related | [01-PRD](01-PRD.md) · [03-Architecture](03-Architecture.md) · [04-UI-UX](04-UI-UX.md) · [05-Development-Plan](05-Development-Plan.md) |

**Conventions.** Each requirement has an ID, a "shall" statement, and a way to test it. **Status** is `Done` (implemented in the current build; tests named in *Test* either exist in `backend/test_*.py` or are the manual check to run) or `Planned` (required for MVP sign-off, not yet built). Units: kW (power), kWh (energy), ₹ (rupees), % SOC (battery state of charge). One cycle = one simulated hour (`CYCLE_HOURS = 1.0`).

---

## 1. Overview

The system simulates a microgrid (solar, battery, grid, essential load, flexible loads) hour by hour. Each hour an AI agent proposes how to meet demand; a deterministic safety layer corrects the proposal; the result is applied and reported, and compared with a fixed-rule controller fed identical inputs. A web dashboard lets viewers run and inspect the simulation.

## 2. User roles and permissions

| Role | Description | Permissions |
|---|---|---|
| **Viewer** (anonymous) | Anyone who opens the web app | Read landing page; create/own one session per browser tab; run cycles and simulations in that session; reset it; read and download its history. Cannot read or modify other sessions. |
| **Script user** | Developer calling the API without a session header (curl, tests, `run_scenarios.py`) | Same as Viewer, on the shared `default` session. |
| **Operator** | Person deploying the service | Sets environment variables (`GROQ_API_KEY`) and `config.py`; reads server logs. No in-app admin UI in MVP. |

There are **no user accounts** in the MVP. Isolation is by session id, not identity.

## 3. Functional requirements

### 3.1 Sensing

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-S1 | The system shall obtain hourly shortwave irradiance (W/m²) for `config.LATITUDE/LONGITUDE` from Open-Meteo, covering 8 days. | Call `fetch_hourly_irradiance()`; length ≥ 192 | Done |
| FR-S2 | If the weather API fails, the system shall use a clear-sky bell curve (0 at night, peak 850 W/m² at noon) and continue. | Block network; cycle completes; log shows fallback message | Done |
| FR-S3 | Cached irradiance older than 6 hours shall be re-fetched when a run starts (reset/simulate), never mid-run. | Set fetched-at to 7 h ago; reset; cache cleared | Done |
| FR-S4 | Solar power (kW) shall be `SYSTEM_CAPACITY_KW × irradiance / 1000`, rounded to 0.01. | 500 W/m² → 5.0 kW | Done |
| FR-S5 | Forecast for the current hour = irradiance × scenario multiplier; actual = forecast × noise, noise ~ N(1, variability) clipped to [0.1, 1.25]. | Sample 1,000 hours; mean ≈ 1, bounds respected | Done |
| FR-S6 | The system shall provide the next 8 hours of solar forecast (`solar_forecast_next_hours`) and set `forecast_solar_kw` to its first element. | Length 8; first element equals `forecast_solar_kw` | Done |
| FR-S7 | Essential load (kW) shall follow the 24-value daily profile × U(0.9, 1.1). | Hour 19 value within 3.8 × [0.9, 1.1] | Done |
| FR-S8 | A water-pump job (1.5 kW, deadline 10:00) shall arrive each hour 06–09; an EV job (3.0 kW, deadline 06:00) each hour 18–22. Job names include the start hour, e.g. `water_pump (07:00)`. | Hour 7 → one pump job named with 07:00 | Done |
| FR-S9 | Jobs deferred last hour shall carry forward; a job with ≤ 1 hour to its deadline (modulo 24) shall be flagged `must_run`. | EV deferred at 22:00 → `must_run` false at 23:00, true at 05:00 | Done |
| FR-S10 | Grid price shall be ₹8 × multiplier by hour: 09–16 ×0.8 ("solar hours"), 18–21 ×1.2 ("peak"), else ×1.0 ("normal"); `price_band` carries the label. (Solar hours are at least 20% cheaper; the peak surcharge is 10–20%, set by each state; we assume 20%.) | Hours 3/10/19 → 8.0/6.4/9.6 and normal/solar hours/peak | Done |
| FR-S11 | Battery SOC shall start at `INITIAL_BATTERY_SOC_PCT` (60%) for a new session; capacity 10 kWh. | First `/cycle` after reset senses SOC 60 | Done |

### 3.2 AI allocation

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-A1 | The system shall send the LLM the scenario, hour, solar now, 8-hour solar forecast, battery SOC and capacity, essential load, flexible jobs (power, deadline, `must_run`), current price and next 8 hours of prices. | Inspect prompt in a unit test | Done |
| FR-A2 | The LLM response shall be requested as JSON matching a strict schema: `solar_used_kw`, `battery_used_kw` (negative = charging), `grid_used_kw`, `defer_loads[]`, `reasoning`. | Schema in `DECISION_RESPONSE_FORMAT` | Done |
| FR-A3 | A response shall be rejected if any power value is missing, non-numeric, boolean or non-finite; if `defer_loads` is not a list of strings; if `reasoning` is empty; or if it defers an unknown job. | `test_allocation_parsing.py` | Done |
| FR-A4 | JSON wrapped in code fences or prose shall be extracted before validation. | Fenced JSON accepted | Done |
| FR-A5 | Rate-limit (429), malformed-JSON and 503/timeout errors shall be retried up to `LLM_MAX_ATTEMPTS` (4), waiting the delay stated in the 429 message (+0.25 s, max 20 s) or exponential back-off. | Fake LLM raising 429 twice then succeeding → decision used | Done |
| FR-A6 | If no valid response is obtained, or the server's AI budget is used up (`ai_blocked_reason`), the system shall use the **fixed rule** (same logic as the rule-based baseline): solar, then battery down to the reserve within the rate limit, then grid; no job deferred. It sets `ai_fallback` and adds an alert starting `AI fallback:`. When the budget is used up the LLM is not called. | `test_allocation_parsing.py`; `test_cycle_accounting.py` (AI off == baseline in all scenarios) | Done |
| FR-A7 | When the forecast missed (`replanned`), the prompt shall state this hour's actual solar and last hour's forecast for it, and ask the agent to keep more battery in reserve. | `test_apply.py` (live) | Done |

### 3.3 Safety layer (applied after every allocation, in this order)

| ID | Requirement | Test (`test_safety_rules.py` case) | Status |
|---|---|---|---|
| FR-SF0 | A `must_run` job listed in `defer_loads` shall be removed from it, with an alert. | Case 5 | Done |
| FR-SF1 | `solar_used_kw` shall not exceed solar generated (+0.01 tolerance); excess is moved to grid with an alert. | Case 1 | Done |
| FR-SF2 | Battery discharge shall not exceed `min((SOC − 20%) × capacity / 1 h, 5 kW)`; excess moved to grid with an alert. | Case 2 | Done |
| FR-SF3 | Battery charging shall not exceed `min(room to 100% / 1 h, 5 kW, surplus solar)`; the battery is never charged from the grid. | Case 6 | Done |
| FR-SF4 | Supply (solar + discharge + grid) shall be ≥ essential load + non-deferred flexible load; any shortfall is added from grid with an alert. Unused grid import is trimmed. | Cases 3, 4, 7 | Done |
| FR-SF5 | Surplus solar shall charge the battery up to FR-SF3 limits even if the AI did not ask; `solar_used_kw` remains solar serving load only. | Case 7b | Done |
| FR-SF6 | Solar left after load and charging shall be exported, capped at `GRID_EXPORT_LIMIT_KW`; any remainder is recorded as curtailed. | Case 7c | Done |
| FR-SF7 | Differences ≤ 0.01 kW shall not trigger overrides or alerts. | "shifted 0.0 kW" never appears in a 2-day run | Done |
| FR-SF8 | Battery power of exactly zero shall be reported as `0.0`, never `-0.0`. | Night hours in a run | Done |

### 3.4 Forecast check, apply, report

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-R1 | New SOC = old SOC − battery kW × 1 h / capacity × 100, clamped to [0, 100]. | 60%, 2 kW discharge, 10 kWh → 40% | Done |
| FR-R2 | Jobs named in `defer_loads` shall be marked `deferred: true`; others `false`. | `test_apply.py` | Done |
| FR-R3 | Sensing shall compute `forecast_miss_kw` = actual solar − last cycle's forecast for this hour, and set `replanned` ("forecast missed") when its magnitude > 1.0 kW, **before** allocation. Each hour is decided and applied exactly once (the old loop back from apply to allocate applied the battery twice). | `test_safety_rules.py` 9b; `test_cycle_accounting.py` (SOC moves once per hour over 48 h) | Done |
| FR-R4 | Report shall include: served load (essential + non-deferred jobs), import cost, export credit, net cost, baseline (grid-only) cost, savings, CO₂ avoided (0.71 kg/kWh, export counted as avoided), solar available/self-used/curtailed, deferred jobs, alerts, replanned (forecast-missed) flag and `forecast_miss_kw`. | Case 9, 11 | Done |

### 3.5 Rule-based comparison

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-C1 | Each cycle shall also run a fixed-rule controller on the same solar, essential load, newly arrived jobs and price: solar → battery to reserve → grid; surplus charges battery then exports; never defers; own SOC starting at 60%. | Case 10 | Done |
| FR-C2 | The session comparison shall report: hours, grid kWh (agent/rules), grid reduction %, net cost (agent/rules), extra savings, renewable share %, solar generated, self-use % (agent/rules), export kWh (agent/rules), solar wasted, AI-fallback hours, safety-override hours. | `/state` → `comparison` keys present | Done |

### 3.6 Sessions and API

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-API1 | Session id shall be read from header `X-Session-Id`, or query `session` for download links; sanitised to `[A-Za-z0-9_-]`, max 64 chars; empty → `default`. | `test_sessions.py` | Done |
| FR-API2 | At most 100 sessions shall be kept; the least recently used is evicted. | Create 101 sessions; first is gone | Done |
| FR-API3 | Requests for the same session shall be processed one at a time (per-session lock). | Two concurrent `/cycle` → cycle numbers 1 and 2, no duplicates | Done |
| FR-API4 | Endpoints (all JSON unless noted): `GET /health`, `GET /scenarios`, `GET /state`, `POST /cycle`, `POST /simulate {scenario, days}`, `POST /reset {scenario?}`, `GET /history`, `GET /history/csv` (text/csv), `GET /history/download` (text/plain). | See [03-Architecture §5](03-Architecture.md#5-api) | Done |
| FR-API5 | `POST /simulate` shall reset the session and run `days × 24` cycles, returning summary + all cycles. | 1-day call returns 24 cycles | Done |
| FR-API6 | Invalid input (unknown scenario, `days` outside 1–7) shall return **HTTP 400** with `{"error": "..."}`. *(Currently returns 200 with the error body.)* | `POST /simulate {"days": 9}` → 400 | **Planned** |
| FR-API7 | `GET /history/csv` and `/history/download` on an empty session shall return **HTTP 404** with `{"error": "..."}`. *(Currently 200.)* | New session → 404 | **Planned** |

### 3.7 Frontend

| ID | Requirement | Test | Status |
|---|---|---|---|
| FR-UI1 | Each browser tab shall create a session id (stored in `sessionStorage`) and send it on every API call. | Two tabs → different ids in request headers | Done |
| FR-UI2 | On load, the dashboard shall restore state, chart (last 20 cycles), totals and scenario from `/state` and `/history`. | Run 3 cycles, refresh → 3 cycles shown | Done |
| FR-UI3 | "Run 1 hour" shall animate pipeline steps and mark Allocate "forecast missed: cautious" when the forecast missed. | Visual | Done |
| FR-UI4 | "Simulate N days" (label follows the days input) shall reset, then call `/cycle` N times, updating progress (hour i/N) and the latest reasoning after each hour. | 1 day → progress reaches 24/24 | Done |
| FR-UI5 | The situation panel shall show hour + day + scenario, solar now vs forecast (highlight when miss > 1 kW), price + band, essential demand + jobs running/waiting. | Visual at 19:00 → ₹9.60 "Evening peak" | Done |
| FR-UI6 | The energy flow shall show solar→load, battery→load, grid→load, solar→battery when charging, and "exporting X kW" when exporting. | Noon on sunny day shows charging/export | Done |
| FR-UI7 | Errors shall distinguish "can't reach the backend" (network) from "backend returned an error (status)". | Stop backend → network message | Done |
| FR-UI8 | A "Load saved results" option shall display pre-computed results for a scenario without calling the AI. | Offline backend → saved results render | **Planned** |
| FR-UI9 | The landing page shall show a results strip with numbers taken from `sample_results/`. | Numbers match JSON | **Planned** |

## 4. Business rules

| ID | Rule |
|---|---|
| BR1 | Safety rules always override the AI (FR-SF0–SF6). The AI never has the final word on reserve, rates, essential load or deadlines. |
| BR2 | Energy priority for serving load: solar → battery (above reserve) → grid. |
| BR3 | The battery is charged only from solar, never from the grid. |
| BR4 | Export happens only after load and battery charging are satisfied; it is credited at `EXPORT_CREDIT_RS_PER_KWH`. |
| BR5 | A flexible job may be deferred any number of times but must run in the last hour before its deadline. |
| BR6 | Essential load is never deferred or dropped. |
| BR7 | Savings are always stated against a baseline with the same inputs: grid-only (per-cycle report) and fixed rules (comparison). |
| BR8 | All simulated inputs (demand, forecast error) are labelled as simulated in the UI and documentation. |

## 5. Data requirements

### 5.1 Session state (`GridState`, per session, in memory)
`sim_hour` int ≥ 0 · `scenario` ∈ {sunny, normal, cloudy, monsoon} · `solar_kw` ≥ 0 · `forecast_solar_kw` ≥ 0 · `solar_forecast_next_hours` float[8] · `previous_forecast_kw` float|null · `battery_soc_pct` [0,100] · `battery_capacity_kwh` > 0 · `critical_load_kw` > 0 · `flexible_loads[]` {name, power_kw > 0, deadline "HH:MM", deadline_hour 0–23, deferred bool, must_run bool} · `new_flexible_loads[]` · `grid_price_per_kwh` > 0 · `price_band` · `decision` {solar_used_kw ≥ 0, battery_used_kw, grid_used_kw ≥ 0, grid_export_kw ≥ 0, solar_curtailed_kw ≥ 0, defer_loads[], reasoning} · `reasoning` · `alerts[]` · `deviation_detected` · `replanned` · `report` · `comparison`.

### 5.2 Cycle history entry (per cycle)
`cycle`, `sim_hour`, `scenario`, `timestamp`, `solar_kw`, `battery_kw`, `grid_kw`, `export_kw`, `load_kw`, `deferred_loads[]`, `battery_soc_pct`, `reasoning`, `alerts[]`, `replanned`, `savings_rs`, `carbon_avoided_kg`, `grid_price_rs`, `agent_cost_rs` (net), `solar_available_kw`, `solar_self_used_kw`, `solar_curtailed_kw`, `rule_grid_kw`, `rule_cost_rs` (net), `rule_export_kw`, `rule_solar_self_used_kw`, `ai_fallback`, `forecast_miss_kw`, `seed`.

### 5.3 Persistence and retention
- Session state and history: in memory only; lost on server restart; evicted by LRU (FR-API2).
- Server log `backend/logs/surya_saarthi_log.txt`: append-only text, all sessions (operator only).
- Saved results: `backend/sample_results/<scenario>.json` (versioned in git).
- No personal data is collected.

## 6. Validations

| Input | Rule | On failure |
|---|---|---|
| `scenario` | Must be a key of `WEATHER_SCENARIOS` | 400 (FR-API6) |
| `days` | Integer 1–7 | 400 (FR-API6) |
| `X-Session-Id` / `session` | Sanitised; never rejected | Falls back to `default` |
| LLM output | FR-A3 | Safe fallback (FR-A6) |
| Dashboard days input | Clamped to 1–7 client-side | — |

## 7. Authentication and authorization

- **AUTH1** The MVP has no login; all endpoints are public. *(Done — deliberate, for a public demo.)*
- **AUTH2** A session can only be read or changed by a client presenting its id; ids are random UUIDs, not guessable sequences. *(Done)*
- **AUTH3** `GROQ_API_KEY` is read from the server environment only; it is never sent to the browser or logged. *(Done)*
- **AUTH4** *(Planned, post-MVP)* If the service ever controls real equipment, write endpoints (`/cycle`, `/simulate`, `/reset`) shall require an authenticated operator role.

## 8. Error handling

| Situation | Required behaviour | Status |
|---|---|---|
| Weather API down | Clear-sky fallback (FR-S2) | Done |
| LLM 429 / malformed / 503 | Retry (FR-A5), then fallback (FR-A6) | Done |
| LLM key missing | Fallback every cycle, alert shown | Done |
| Invalid request | 400 + JSON error (FR-API6) | Planned |
| Empty history download | 404 + JSON error (FR-API7) | Planned |
| Unhandled server error | 500; frontend shows "backend returned an error (500)" | Done |
| Backend unreachable | Frontend shows "can't reach the backend at …" | Done |

## 9. Edge cases (each must be handled without error)

1. Night: solar = 0 → no solar used, no export, no charging.
2. Battery at 20%: no discharge; at 100%: no charging, surplus exported.
3. First cycle: `previous_forecast_kw` is null → `forecast_miss_kw` null, not flagged.
4. Several deferred jobs with the same deadline → all run by the deadline (may raise grid use that hour).
5. Deadline wraps midnight (EV 22:00 → 06:00).
6. AI defers a `must_run` job → removed (FR-SF0).
7. AI names a job that doesn't exist → response rejected → fallback.
8. AI returns negative solar or grid → clamped to 0.
9. Surplus larger than export limit → remainder curtailed.
10. 101st session → oldest evicted.
11. Scenario switched on reset mid-day → the next cycle's forecast check may flag a miss (planned cautiously).
12. Page refresh during a simulation → loop stops; server keeps completed cycles; dashboard restores them.

## 10. Non-functional requirements

### Security
| ID | Requirement | Status |
|---|---|---|
| NFR-S1 | No secrets in the repo; `.env` git-ignored; `.env.example` provided. | Done |
| NFR-S2 | Session ids sanitised (FR-API1); no user input reaches file paths or shell. | Done |
| NFR-S3 | CORS: allow all origins in MVP (public read-mostly demo); restrict to the deployed frontend origin in production. | Done / Planned |
| NFR-S4 | Dependencies pinned (`requirements.txt`, `package-lock.json`). | Done |
| NFR-S5 | Limit AI-backed calls per session (e.g. ≤ 200 cycles/hour) to protect API quota. | Planned |

### Privacy and compliance
| ID | Requirement | Status |
|---|---|---|
| NFR-P1 | No cookies, analytics or third-party requests from the browser; fonts and icons are served from the site. Only the random session id is stored (sessionStorage). | Done (verified: all browser requests go to the site or the backend) |
| NFR-P2 | Only simulated numbers are sent to Groq; only the fixed site coordinates to Open-Meteo. | Done |
| NFR-P3 | A Privacy & Disclaimer page (`#/privacy`) states what is stored, what is sent where, that it is a simulation not for real equipment, and no warranty; linked from both footers. | Done |
| NFR-P4 | Open-Meteo attribution ("Weather data by Open-Meteo.com", CC BY 4.0) next to where its data appears (landing and dashboard footers); third-party credits on `#/credits` and in `THIRD_PARTY_NOTICES.md`; licence headers kept in the built JS. | Done |
| NFR-P5 | Public claims match the sources: ToD solar hours at least 20% cheaper; peak 10–20% costlier, set by each state; we assume 20%. | Done |

### Performance
| ID | Requirement | Status |
|---|---|---|
| NFR-P1 | Non-AI endpoints (`/health`, `/scenarios`, `/state`, `/history`) respond in < 200 ms (p95) locally. | Done |
| NFR-P2 | `/cycle` completes in < 5 s (p95) when the AI API is not rate-limited. | Done |
| NFR-P3 | First JS download < 300 KB; heavy visuals lazy-loaded. | Done (247 KB) |
| NFR-P4 | The dashboard loop (not `/simulate`) is used for long runs so no single HTTP request exceeds host timeouts. | Done |

### Reliability and usability
| ID | Requirement | Status |
|---|---|---|
| NFR-R1 | AI fallback hours ≤ 5% in a 2-day run on the free tier. | Verified per run |
| NFR-U1 | Usable at 390 px width without horizontal scroll. | Done |
| NFR-U2 | Respects `prefers-reduced-motion` (no animated backgrounds, no count-up). | Done |
| NFR-U3 | Text contrast ≥ 4.5:1 for body text. | Done |

## 11. Acceptance criteria

The build is accepted when:
1. All `Done` requirements above pass their listed tests.
2. `python test_safety_rules.py`, `python test_allocation_parsing.py`, `python test_sessions.py` pass with no network access.
3. A 2-day `run_scenarios.py` produces, for every scenario: 0 reserve/rate violations, 0 unpowered essential load, 0 missed deadlines, AI fallback ≤ 5%.
4. `npm run build` succeeds with no errors.
5. All `Planned` items marked MVP (FR-API6, FR-API7, FR-UI8, FR-UI9, NFR-S5) are implemented and tested, or explicitly deferred in the Development Plan.
