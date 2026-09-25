# Surya Saarthi — Product Requirements Document (PRD)

| | |
|---|---|
| Product | **Surya Saarthi** ("charioteer of the sun"): an AI agent for solar + battery + grid microgrids |
| Context | Smart India Hackathon 2026, PS **SIH26200** (AICTE) — "Innovative ideas that help manage and generate renewable / sustainable sources more efficiently" · Theme: Renewable / Sustainable Energy · Category: Software |
| Status | MVP built (simulation-backed); this document defines the MVP and what is deliberately left out |
| Related | [02-SRS](02-SRS.md) · [03-Architecture](03-Architecture.md) · [04-UI-UX](04-UI-UX.md) · [05-Development-Plan](05-Development-Plan.md) |

---

## 1. Problem

India is installing rooftop solar and batteries quickly (for example under **PM Surya Ghar Muft Bijli Yojana**), but the software that decides *where each unit of power comes from* is usually a fixed rule: "use solar, then battery until X%, then grid". That rule:

1. **Ignores time-of-day prices.** Since the 2023 Time-of-Day (ToD) tariff rules, power is ≥20% cheaper in solar hours and ≥20% costlier at the evening peak. A fixed rule drains the battery before the peak and then buys expensive grid power.
2. **Ignores the weather forecast.** It cannot keep battery in reserve when clouds are coming.
3. **Wastes or under-values surplus solar.** Surplus is exported cheaply (or curtailed) instead of being stored for the peak.
4. **Runs flexible loads at the wrong time.** Water pumps and EV charging run whenever they are switched on, often at peak price.
5. **Cannot explain itself.** Owners and operators never learn why the system did what it did, or how much it saved.

Adding "AI" alone is not the answer: a language model can make a confident but unsafe decision (for example draining the battery to 0% or dropping an essential load).

## 2. Solution summary

An **AI agent that plans the microgrid every hour** — weighing solar, battery, grid price, forecast and flexible jobs, and explaining each decision in one sentence — **wrapped in hard safety rules that always win**. A fixed-rule controller runs on the same inputs every hour, so the benefit is measured, not claimed.

## 3. Target users

| Persona | Who | What they need |
|---|---|---|
| **P1 — Prosumer household** | Home with 3–10 kW rooftop solar + battery (PM Surya Ghar) | Lower bills without micromanaging; confidence the battery and essentials are safe |
| **P2 — Campus / facility energy manager** | College, hostel, small institution with a solar + battery block | Peak-cost reduction, flexible-load scheduling (pumps, EV), a report they can show management |
| **P3 — Village / farm microgrid operator** | Community or agricultural microgrid, solar pumps | Reliable essential supply, pumps run on solar, simple view of what is happening |
| **P4 — Evaluator / demo viewer** (MVP primary) | SIH judges, mentors, DISCOM or MNRE reviewers | Understand the idea in minutes, see it decide live, see measured savings vs fixed rules |

For the MVP, **P4 is the primary user** (the product is demonstrated in simulation); P1–P3 shape the scenarios and metrics.

## 4. Goals and non-goals

### Goals
- **G1** Use less grid energy and cost less than a fixed-rule controller under the same conditions.
- **G2** Never violate a safety limit (battery reserve, charge/discharge rate, essential load, job deadlines) — regardless of what the AI proposes.
- **G3** Make every decision explainable and visible (reasoning, overrides, forecast misses).
- **G4** Let a first-time viewer understand and run the demo in under 3 minutes, on laptop or phone.
- **G5** Stay honest: all numbers traceable to stated assumptions; simulated inputs clearly labelled.

### Non-goals (MVP)
- Controlling real hardware (inverters, relays, meters).
- User accounts, billing, or multi-site fleet management.
- Training or fine-tuning a model; forecasting beyond what the weather API provides.

## 5. Core features (MVP)

| ID | Feature | Status |
|---|---|---|
| F1 | **Hourly agent loop**: sense → AI allocate → safety check → apply → replan-if-needed → report | Done |
| F2 | **Real solar data**: Open-Meteo irradiance for the site + 8-hour solar forecast; per-scenario forecast error (passing clouds) | Done |
| F3 | **AI allocation with reasoning**: LLM proposes solar/battery/grid split and which flexible jobs to defer, with a one-sentence reason | Done |
| F4 | **Hard safety layer**: 20% reserve, 5 kW rate limits, no phantom solar, all non-deferred load powered, deadline enforcement, surplus solar stored, tolerance for rounding | Done |
| F5 | **Replanning**: if actual solar misses the forecast by > 1 kW, decide again (once) with a more conservative instruction | Done |
| F6 | **Time-of-Day tariff** (solar hours −20%, peak +20%) with 8 hours of prices visible to the agent | Done |
| F7 | **Flexible loads**: water pump and EV jobs can be deferred, carry forward, and must run before their deadline | Done |
| F8 | **Net-metering export** of surplus solar, credited at a configurable rate | Done |
| F9 | **Rule-based comparison**: fixed-rule controller on identical inputs; grid kWh, net cost, self-use %, export, renewable share | Done |
| F10 | **Live dashboard**: situation panel, energy-flow diagram, reasoning, battery gauge, overrides, session impact, comparison card, history chart, history log | Done |
| F11 | **Weather scenarios** (sunny / normal / cloudy / monsoon) and **1–7 day simulation** | Done |
| F12 | **Exports**: per-hour CSV and readable text log | Done |
| F13 | **Separate session per browser tab** (safe for several viewers at once) | Done |
| F14 | **Reliability**: retry on rate limits / malformed AI output; deterministic safe fallback if the AI is unavailable | Done |
| F15 | **Saved demo results** (pre-computed runs per scenario) so the demo works without the AI API | Planned (MVP) |
| F16 | **Landing page** explaining problem, loop and safety thesis; results strip | Done (results strip Planned) |

## 6. MVP scope

**In:** F1–F16 above, one site configuration (Delhi, 10 kW solar, 10 kWh battery), simulated demand, web dashboard (desktop + mobile), public demo without login.

**Out (see §11):** hardware control, accounts, database persistence, multi-site, mobile apps, custom ML forecasting.

## 7. User stories

| ID | As a… | I want to… | So that… | Feature |
|---|---|---|---|---|
| US1 | viewer | open the site and understand the problem and idea in one scroll | I know what I am about to see | F16 |
| US2 | viewer | run one hour and watch each pipeline stage | I see how a decision is made | F1, F10 |
| US3 | viewer | see the time, sunlight vs forecast, price and demand the agent saw | I understand *why* it decided | F10 |
| US4 | viewer | read the agent's one-sentence reasoning | the decision is explainable | F3 |
| US5 | viewer | see when a safety rule overrode the AI, and why | I trust it cannot do something unsafe | F4 |
| US6 | viewer | pick a weather scenario and run 1–7 days | I can test it in sunny and monsoon conditions | F11 |
| US7 | energy manager | see grid use and cost vs a fixed-rule controller | I know the benefit is real | F9 |
| US8 | energy manager | see pumps and EV charging moved to cheaper hours but still finish on time | flexible jobs cost less without missing deadlines | F7 |
| US9 | prosumer | know how much solar I used, stored, exported or wasted | I get full value from my panels | F8, F9 |
| US10 | viewer | download results as CSV / a log | I can verify numbers or build charts | F12 |
| US11 | viewer | keep my run if I refresh, and not see someone else's run | the demo behaves predictably | F13 |
| US12 | viewer | have the demo keep working if the AI service is slow or down | the demo never looks broken | F14, F15 |

## 8. Success metrics

| Metric | Target (MVP) | How measured |
|---|---|---|
| Grid energy vs fixed rules | ≥ 15% less on sunny/normal days | `vs_rule_based.grid_reduction_pct` from `run_scenarios.py` |
| Net cost vs fixed rules | Lower in every scenario | `extra_savings_rs` > 0 |
| Safety violations after the safety layer | **0** | Offline tests + audit of every simulated hour |
| Essential-load outages | **0** | Every hour: supplied ≥ essential + non-deferred load |
| Missed flexible-job deadlines | **0** | Every job runs before `deadline_hour` |
| AI fallback hours | ≤ 5% of hours | `ai_fallback_hours / hours` |
| Time to first decision for a new viewer | < 60 s from landing | Manual test |
| First-load JS size | < 300 KB | `npm run build` output |

Measured results for the current build are recorded in `backend/sample_results/` and quoted in the pitch deck.

## 9. Assumptions

| Area | Assumption |
|---|---|
| Site | Delhi; 10 kW solar; 10 kWh battery starting at 60%; 20% reserve; 5 kW max charge/discharge |
| Tariff | ₹8/kWh base; ToD: 09–17 ×0.8, 18–22 ×1.2 |
| Export | ₹3/kWh credit — **assumption**, varies by state/DISCOM; export ≤ system size |
| CO₂ | 0.71 kg/kWh (CEA CO₂ Baseline Database v21.0); exported solar counts as avoided grid energy |
| Demand | Simulated daily profile 1.5–3.8 kW (±10%); pump 1.5 kW 06–09 due 10:00; EV 3 kW 18–22 due 06:00 |
| Weather | Open-Meteo forecast is "the forecast"; actual = forecast × noise (sunny 5%, normal 20%, cloudy 35%, monsoon 45%) |
| AI | Groq-hosted `openai/gpt-oss-20b`, free tier (8,000 tokens/min) |
| Time step | 1 simulated hour per cycle |

## 10. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| AI proposes unsafe allocation | Battery damage / outage in a real system | Deterministic safety layer after every AI call (F4); tested offline |
| AI API rate-limited or down during demo | Slow or failed demo | Retry with backoff; safe fallback; saved demo results (F15) |
| Judges question simulated demand | Credibility | Label "simulated demand" everywhere; assumptions table; roadmap to metered data |
| Results look cherry-picked | Credibility | Same inputs for agent and rules; 4 scenarios; CSV export |
| Render free tier sleeps | ~50 s cold start | Open backend before presenting; optional keep-alive |
| Export credit assumption wrong for a state | Savings mis-stated | Configurable; stated as assumption |
| Public demo abused (API cost) | Groq quota exhausted | Per-session limits (Planned, SRS NFR-S5) |

## 11. Out of scope (explicitly not in MVP)

- Hardware integration (Modbus/MQTT to inverters, smart meters, relays) — architecture leaves a seam for it.
- User accounts, login, roles beyond "viewer"; admin console.
- Persistent database; long-term history across server restarts.
- Multi-site / fleet coordination; peer-to-peer energy trading.
- Native mobile apps; push notifications.
- Custom ML forecasting models; battery-degradation cost modelling.
- Multiple languages (English only in MVP).

## 12. Acceptance criteria (MVP)

The MVP is accepted when all of the following hold:

1. **AC1** A viewer can go from landing page to a completed first cycle in under 60 seconds with no instructions.
2. **AC2** Every cycle shows: situation panel, energy flow, reasoning, battery %, overrides, session impact, and comparison card.
3. **AC3** Across a 2-day run of each of the 4 scenarios: 0 reserve violations, 0 rate-limit violations, 0 unpowered essential load, 0 missed deadlines.
4. **AC4** The agent's net cost is lower than the rule-based controller's in every scenario of the saved results.
5. **AC5** Offline tests (`test_safety_rules.py`, `test_allocation_parsing.py`, `test_sessions.py`) pass.
6. **AC6** Two browser tabs running at once never see each other's history.
7. **AC7** With the AI key removed, cycles still complete using the safe fallback and are labelled as such.
8. **AC8** The dashboard is usable at 390 px width with no horizontal scrolling.
9. **AC9** Every number on the landing page and pitch deck is reproducible from `run_scenarios.py` output and the assumptions table.
