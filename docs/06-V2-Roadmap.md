# Surya Saarthi v2 — Roadmap

| | |
|---|---|
| Started | 27 Sep 2026, from the SIH `sih-improvements` branch (commit `e4006ec`) |
| Location | `Documents/surya-saarthi-v2`, branch `main`, no remote yet |
| SIH copy | `Documents/microgrid-agent-sih` is left untouched |

## Positioning

**Surya Saarthi keeps essential power on through power cuts at the lowest cost and least battery wear. An optimizer decides, hard safety rules guard, and an AI understands the operator and explains every decision in plain Hindi or English.**

- **For:** sites with solar + battery + power cuts, often with a diesel genset — rural mini-grids, schools and health centres, small businesses, homes with an inverter and battery. PM Surya Ghar stays as context, not the main user (those homes are mostly on-grid without batteries).
- **Why:** puts the LLM on language (operator instructions, explanations), not arithmetic; answers "why not an optimizer?" and "who has a battery?"; specific to India (outages, gensets, time-of-day tariffs, Hindi).

## Phases

Status: ✅ done · 🔄 in progress · ⬜ not started

### Phase 0 — Stop the bleeding (week 1) ✅

| Task | Status | Notes |
|---|---|---|
| Fix the replan double-apply bug | ✅ | The forecast check moved into `sense`, before the decision; the graph no longer loops, so each hour is decided and applied once. Reproduced first as a failing test (`test_cycle_accounting.py`, hour 12: battery charged then discharged in the same hour). |
| Fixed random seeds | ✅ | Clouds and demand noise keyed on (seed, hour); `seed` on `/reset` and `/simulate`, recorded per hour and in the CSV. `run_scenarios.py` uses seed 1. |
| Better fallback | ✅ | When the AI is unavailable or the budget is used up, the fixed rule decides (same logic as the baseline). A run with the AI off matches the baseline exactly in all 4 scenarios — so any difference in a real run is the AI's effect. |
| Protect the live demo | ✅ | AI budget per rolling 24 h (150 whole demo, 48 per tab), 300 requests/min per tab, `FRONTEND_ORIGINS` for CORS. All env-configurable; see README. |
| Forecast correction for the next hours | Moved to Phase 1 | With today's noise model, each hour's cloud noise is independent, so correcting the next hours from this hour's miss would make forecasts *worse*. It becomes useful once real forecast errors (which persist for hours) come from Open-Meteo's archive. |
| Team: contact 3–4 installers / mini-grid operators / DISCOM engineers | ⬜ | Start now; quote only conversations that happened. |

### Phase 1 — Foundation and first honest results (weeks 1–4) ⬜

| Task | Est. |
|---|---|
| Realistic physics: solar losses + inverter limit (no more > 10 kW from a 10 kW system), battery round-trip efficiency + wear cost | 3–4 days |
| Real weather: Open-Meteo Historical Forecast API vs Historical Weather API for past days; then forecast correction | 2 days |
| Power cuts + genset: scheduled cut windows, outage-likelihood profile from Prayas ESMI data, islanded mode (essentials only), genset minimum run time and fuel | 4–5 days |
| Optimizer: 24 h LP/MPC (PuLP or CVXPY + HiGHS) | 4–5 days |
| Benchmark: rules vs LLM vs optimizer vs hybrid over real days — cost, grid kWh, battery wear, diesel hours, essential-load outages, overrides | 3 days |

**Checkpoint (week 4):** the results table for the deck. Groq: the LLM variant needs ~1k tokens × 24+ calls per simulated day — run ~10 days spread over several dates, or use a small paid tier.

### Phase 2 — Differentiators (weeks 5–8) ⬜

- LLM context interpreter: Hindi/English operator notes ("kal shaam 7 se 10 bijli jayegi") → checked constraints; the LLM never commands a device.
- Grounded explanations from the optimizer's own facts, phrased in Hindi or English, checked for truthfulness.
- Software BMS: cell-level model, dynamic charge/discharge limits, health tracking, BLAST-Lite wear; the safety shield obeys BMS limits.
- What-if panel (solar −40%, outage window, battery health, tariff) — runs without the AI.
- Demand-response events, measured against a baseline day.

### Phase 3 — Credibility and delivery (weeks 9–12) ⬜

- ESP32 testbed + model synced to it (digital twin) + condition monitoring ("clean your panels").
- Edge fallback: safety rules + cached 24 h schedule on the device.
- Security: logins on control endpoints, signed setpoints.
- Deploy, deck, 90-second video, paper draft.

**Cut order if time runs short:** multi-site demo → attack detection → testbed sync. Never cut the benchmark.

## Open decisions (team)

1. Next SIH deadline (sets how much of Phase 1 comes before the deck).
2. GitHub: a new repository for v2, or a branch in the existing one.
3. Budget for testbed parts and/or Groq's paid tier.

## Do not claim

Accuracy numbers from simulated data · "predicts failures" · "detects cyberattacks" without "tested on simulated attacks" · "digital twin" before it is synced to real hardware · any result from runs made before the Phase 0 fix.
