# Surya Saarthi — Product Requirements Document (PRD)

| | |
|---|---|
| Product | **Surya Saarthi** ("charioteer of the sun"): an energy manager for sites with solar, a battery and often a diesel genset |
| Context | Smart India Hackathon 2026, PS **SIH26200** (AICTE) — "Innovative ideas that help manage and generate renewable / sustainable sources more efficiently" · Theme: Renewable / Sustainable Energy · Category: Software |
| Version | **v2** (27 Sep 2026). v1 (the SIH submission) lives in the separate `microgrid-agent-sih` repo |
| Status | Built and benchmarked in simulation; not connected to real equipment |
| Related | [02-SRS](02-SRS.md) · [03-Architecture](03-Architecture.md) · [04-UI-UX](04-UI-UX.md) · [05-Development-Plan](05-Development-Plan.md) · [06-V2-Roadmap](06-V2-Roadmap.md) · [07-Benchmark-Results](07-Benchmark-Results.md) |

---

## 1. Problem

India is adding rooftop solar and batteries quickly (for example under **PM Surya Ghar Muft Bijli Yojana**), and many homes, schools, clinics, small businesses and village mini-grids already keep a battery — and often a diesel genset — because **the grid goes out**. The software deciding *where each unit of power comes from* is usually a fixed rule: "solar, then battery down to X%, then grid (or genset)". That rule:

1. **Is caught out by power cuts.** It drains the battery at 6 pm, so when the evening cut starts the diesel genset has to run: more cost, noise and CO₂.
2. **Ignores time-of-day prices.** Since the 2023 Time-of-Day tariff rules, power is at least 20% cheaper in solar hours and 10–20% costlier at the evening peak (set by each state; we assume 20%).
3. **Ignores the forecast and battery wear.** It can't keep charge back for a cloudy afternoon, and treats battery cycles as free.
4. **Runs flexible loads at the wrong time.** Pumps and EV charging run when switched on, often at peak price.
5. **Can't take instructions or explain itself.** An operator can't tell it "the power goes at 7 tonight", and never learns why it did what it did — especially not in Hindi.

Adding an LLM alone is not the answer: a language model is unreliable at arithmetic and can make a confident but unsafe decision.

## 2. Solution summary

**An optimizer decides, hard safety rules guard, and an AI understands the operator and explains every decision in plain English or Hindi.**

- Every hour a **24-hour optimizer** plans solar, battery, grid, genset and flexible jobs together (prices, forecast, power cuts, battery wear, battery limits), applies the first hour and plans again next hour.
- **Hard safety rules and a software battery management system** check every decision, whoever made it.
- **The AI does language:** it reads operator notes ("kal shaam 7 se 10 bijli jayegi") into checked constraints, confirmed before they apply. An **AI mode** lets the LLM decide instead, for comparison.
- **Explanations** in English and Hindi are built from the plan's own numbers.
- A **fixed-rule controller** runs on identical conditions every hour, so the benefit is measured, not claimed.

## 3. Target users

| Persona | Who | What they need |
|---|---|---|
| **P1 — Home with solar and backup** | Rooftop solar (e.g. PM Surya Ghar) plus an inverter battery for power cuts | Essentials on through cuts, lower bills, no micromanaging |
| **P2 — School, clinic or small business** | Solar + battery + diesel genset | Essentials on with less diesel; pumps and EV charging at cheaper hours; a report for management |
| **P3 — Village / farm mini-grid operator** | Community or agricultural mini-grid, solar pumps | Reliable essential supply; plain-language explanations in Hindi; tell the system about planned cuts |
| **P4 — Evaluator / demo viewer** (primary today) | SIH judges, mentors, DISCOM or MNRE reviewers | Understand in minutes, see it decide, see honest measured results |

## 4. Goals and non-goals

### Goals
- **G1** Lower running cost (grid + battery wear + diesel) than a fixed-rule controller on the same conditions, with and without power cuts.
- **G2** Never violate a safety limit (battery reserve, BMS limits, essential load, job deadlines, no grid in a cut) — whoever proposes the decision.
- **G3** Make every decision explainable, in English and Hindi, from the plan's own numbers.
- **G4** Let operators give instructions in their own words, with confirmation before anything changes.
- **G5** Stay honest: every number traceable to recorded data and stated assumptions; simulated inputs labelled.

### Non-goals (today)
- Controlling real hardware (interface exists: signed 24-hour plan; no device connected).
- Accounts, billing, multi-site fleets.
- Training a model; cell-level battery modelling.

## 5. Features

| ID | Feature | Status |
|---|---|---|
| F1 | **Hourly pipeline**: sense (+ forecast check) → decide → safety & BMS limits → apply → explain & report, one pass per hour | Done |
| F2 | **Weather**: live forecast in the demo; recorded weather (actual + day-ahead forecast actually issued) in the benchmark | Done |
| F3 | **Three controllers**: optimizer (default, 24 h MILP, MPC), AI (LLM), fixed rule (baseline and fallback) | Done |
| F4 | **Safety and plant model**, same for every controller: 20% reserve, BMS limits, solar serves load first, no grid charging, all non-deferred load powered, deadlines, surplus stored then exported | Done |
| F5 | **Forecast check**: > 1 kW miss → this hour planned cautiously (checked before deciding) | Done |
| F6 | **Time-of-Day tariff** (solar hours −20%; peak +20%, the surcharge being 10–20% by state) | Done |
| F7 | **Flexible jobs** (water pump, EV) deferred to cheaper hours, done by their deadline | Done |
| F8 | **Net-metering export** at a configurable credit | Done |
| F9 | **Power cuts and diesel genset**: cut windows, essentials only, battery then genset (minimum load) then unserved | Done |
| F10 | **Realistic physics**: PVWatts-style solar, battery efficiency, wear cost, state of health, diesel fuel and CO₂ | Done |
| F11 | **Software BMS**: live charge/discharge limits (tapers, temperature), alarms, injectable faults | Done (pack level) |
| F12 | **Operator notes** (Hindi/Hinglish/English) → power cuts, battery targets, grid limits; confirm before applying | Done |
| F13 | **Explanations in English and Hindi** from the plan's numbers | Done |
| F14 | **What-if** (sun, cut, battery health, tariff, extra load, grid limit), no AI calls | Done |
| F15 | **Demand response**: grid-import caps from the DISCOM | Done |
| F16 | **Comparison vs fixed rule** on identical conditions: cost incl. wear and diesel, grid, diesel, unserved, overrides | Done |
| F17 | **Dashboard** with a 3D energy scene, operator and what-if panels; landing page with results from the benchmark | Done |
| F18 | **Benchmark** on four recorded weeks, grid normal and with power cuts; AI sample | Done |
| F19 | **Signed 24-hour plan** for a site controller (`/plan`) | Done (no device yet) |
| F20 | **Demo protection**: AI budget, rate limit, CORS; per-tab sessions; seeds | Done |
| F21 | Exports (CSV, text log); privacy & disclaimer page; credits | Done |

## 6. Scope

**In:** F1–F21, one site configuration (Delhi, 10 kW solar, 10 kWh battery, 5 kW genset), simulated demand, recorded weather for the benchmark, web dashboard (desktop + mobile), public demo without login.

**Out (see §11):** hardware control, accounts, database, multi-site, mobile apps, cell-level battery model, outage statistics from real data (ESMI).

## 7. User stories

| ID | As a… | I want to… | So that… | Feature |
|---|---|---|---|---|
| US1 | viewer | understand the problem and idea in one scroll | I know what I'm about to see | F17 |
| US2 | viewer | run one hour and see what it decided and why | decisions are explainable | F1, F13 |
| US3 | operator | type "kal shaam 7 se 10 bijli jayegi" and confirm what it understood | the battery is full when the cut starts | F12, F9 |
| US4 | operator | read the explanation in Hindi | I understand it without English | F13 |
| US5 | viewer | see when a safety rule or the BMS stepped in, and why | I trust it can't do something unsafe | F4, F11 |
| US6 | energy manager | see cost, diesel and grid vs a fixed rule on the same conditions | I know the benefit is real | F16, F18 |
| US7 | energy manager | see pumps and EV charging moved to cheaper hours but done on time | flexible jobs cost less | F7 |
| US8 | viewer | ask "what if solar drops 40%?" or "what if there's a cut tonight?" | I see the effect instantly | F14 |
| US9 | DISCOM engineer | set a grid-import limit for an evening window | the site helps with the peak | F15 |
| US10 | viewer | switch who decides (optimizer / AI / fixed rule) | I can compare them myself | F3 |
| US11 | viewer | download results | I can verify numbers | F21 |
| US12 | viewer | keep my run on refresh, separate from others | the demo behaves predictably | F20 |

## 8. Success metrics

| Metric | Target | Result (benchmark, 27 Sep 2026) |
|---|---|---|
| Cost vs fixed rule, grid normal | Lower in every season | **10.0% lower** overall; 7.3–11.5% by season |
| Cost vs fixed rule, daily evening cut | Lower in every season | **26.0% lower**; 25–27% by season |
| Diesel vs fixed rule, with cuts | Lower | **36.7 L vs 97.5 L** over four weeks |
| Safety overrides of optimizer plans | 0 | **0** in 1,344 hours |
| Essential load unserved | 0 | **0** (both controllers) |
| Missed flexible-job deadlines | 0 | 0 (offline tests) |
| Offline tests | All pass | 6 suites pass |
| Browser checks (desktop + 390 px phone) | All pass | 36/36 |

Costs use placeholder battery and diesel prices; see [07-Benchmark-Results](07-Benchmark-Results.md) for caveats.

## 9. Assumptions

| Area | Assumption |
|---|---|
| Site | Delhi; 10 kW solar (PVWatts-style losses, 10 kW inverter); 10 kWh battery from 60%, 20% reserve, 5 kW max, 92% round trip; 5 kW genset |
| Tariff | ₹8/kWh base; 09–17 ×0.8, 18–22 ×1.2 (peak surcharge 10–20% by state; we assume 20%) |
| Export | ₹3/kWh credit — **assumption** |
| Battery wear | ₹12,000/kWh replacement (**placeholder**) ÷ (4,000 cycles × 80%) = ₹3.75 per kWh taken out |
| Diesel | ₹90/L (**assumption**), 2.8 kWh/L (**assumption**), 2.68 kg CO₂/L |
| CO₂ (grid) | 0.71 kg/kWh (CEA CO₂ Baseline Database v21.0) |
| Demand | Simulated daily profile 1.5–3.8 kW (±10%); pump 1.5 kW 06–09 due 10:00; EV 3 kW 18–22 due 06:00 |
| Weather | Demo: live forecast × scenario noise. Benchmark: recorded ERA5 actual + day-ahead forecast |
| Power cuts | Entered by the operator; benchmark uses an **illustrative** daily 19–22 schedule |
| AI | Groq `openai/gpt-oss-20b`, free tier (~200k tokens/day) |

## 10. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A controller proposes something unsafe | Battery damage / outage | Safety layer + BMS after every decision; offline tests; 0 overrides of optimizer plans |
| Groq quota exhausted by the public demo | AI mode stops | AI budget per day and per tab; optimizer needs no AI; fixed-rule fallback |
| Placeholder prices wrong | ₹ results off | All in `config.py`; rerun `benchmark.py` with real quotes |
| Judges question simulated demand / illustrative cuts | Credibility | Labelled everywhere; recorded weather; roadmap to ESMI outage data and metered demand |
| Device without WebGL | Blank page / no 3D | WebGL check + error boundaries; flat diagram fallback |
| Render free tier sleeps | ~50 s cold start | Open `/health` before presenting |

## 11. Out of scope (today)

- Hardware integration (Modbus/MQTT to inverters, meters, relays) — `/plan` is the interface; no device connected.
- Accounts, login, admin console; persistent database.
- Multi-site coordination; peer-to-peer trading.
- Native apps.
- Cell-level battery model, Kalman-filter state estimation.
- Outage probabilities from real supply data (Prayas ESMI).

## 12. Acceptance criteria

1. **AC1** A viewer gets from the landing page to a first decision in under 60 seconds.
2. **AC2** Every hour shows: situation, 3D energy scene (or flat diagram), explanation (EN/HI for the optimizer), battery + BMS, events, session impact, comparison.
3. **AC3** Across the benchmark: 0 reserve violations, 0 rate/BMS violations, 0 unserved essential load, 0 missed deadlines, 0 safety overrides of optimizer plans.
4. **AC4** Optimizer cost lower than the fixed rule in every season, with and without cuts.
5. **AC5** Offline tests pass (`test_cycle_accounting`, `test_safety_rules`, `test_optimizer`, `test_features`, `test_allocation_parsing`, `test_sessions`).
6. **AC6** Two tabs never see each other's runs.
7. **AC7** With the AI key removed, everything except AI mode and AI note reading works; fallbacks are labelled.
8. **AC8** Usable at 390 px with no horizontal scroll; works without WebGL.
9. **AC9** Every number on the landing page comes from `benchmark.py` output.
