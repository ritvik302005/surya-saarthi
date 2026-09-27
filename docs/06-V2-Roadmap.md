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

### Phase 1 — Foundation and first honest results ✅ (compressed, 27 Sep 2026)

| Task | Status | What was built / what's missing |
|---|---|---|
| Realistic physics | ✅ | PVWatts-style solar (losses, heat derating, inverter clipping); battery round-trip efficiency, wear cost, state of health (`physics.py`) |
| Real weather | ✅ | Four recorded weeks of Delhi weather (actual ERA5 + day-ahead forecasts actually issued) in `data/weather_delhi.json` |
| Forecast correction | ✅ measured, off | Helps one season, hurts three (MAE in `docs/07`); stays off |
| Power cuts + genset | ✅ partly | Cut windows, essentials-only islanded mode, genset with minimum load, fuel and CO₂. **Not done:** outage-likelihood profile from Prayas ESMI data (cuts are entered or illustrative) |
| Optimizer | ✅ | 24 h MILP (SciPy/HiGHS), MPC in the pipeline, zero overrides in 1,344 benchmark hours (`optimizer.py`) |
| Benchmark | ✅ | Fixed rule vs optimizer vs perfect-forecast optimizer on 4 seasons × 2 conditions; AI on a 1-day sample. Results: `docs/07-Benchmark-Results.md` |

### Phase 2 — Differentiators ✅ (compressed)

| Task | Status | Notes |
|---|---|---|
| Operator notes → constraints | ✅ | LLM with strict schema + rule-based fallback, validated, confirmed before applying (`notes.py`) |
| Grounded explanations EN/HI | ✅ | Templated from the plan's numbers, rewritten after the safety check from what was applied (`explain.py`). LLM phrasing + truthfulness checker **not done** (templates are true by construction) |
| Software BMS | ✅ partly | Pack-level live limits, temperature derating/cut-off, health, fault injection (`bms.py`). **Not done:** cell-level model, Kalman-filter SOC, BLAST-Lite wear (simple throughput model instead) |
| What-if panel | ✅ | Sun, power cut, battery health, peak tariff, extra load, DISCOM limit; no AI calls (`whatif.py`, `WhatIfPanel.jsx`) |
| Demand response | ✅ | Grid-import caps in the optimizer (notes or what-if); measured against the same day without the cap in what-if |

### Phase 3 — Credibility and delivery ⬜ mostly open

| Task | Status |
|---|---|
| Signed 24 h plan for an edge device, API key | ✅ `GET /plan` (HMAC-SHA256) |
| ESP32 testbed, digital twin synced to it, condition monitoring | ⬜ needs hardware |
| Edge fallback running on a device | ⬜ (interface exists: `/plan` + fixed-rule fallback) |
| Logins on control endpoints | ⬜ (public demo; only `/plan` is key-protected) |
| Deploy v2, deck, video, paper | ⬜ needs the GitHub decision |
| Stakeholder interviews | ⬜ team |
| Multi-site coordination, attack detection | ⬜ cut (as planned) |

## Open decisions (team)

1. Next SIH deadline (sets how much of Phase 1 comes before the deck).
2. GitHub: a new repository for v2, or a branch in the existing one.
3. Budget for testbed parts and/or Groq's paid tier.

## Do not claim

Accuracy numbers from simulated data · "predicts failures" · "detects cyberattacks" without "tested on simulated attacks" · "digital twin" before it is synced to real hardware · any result from runs made before the Phase 0 fix.
