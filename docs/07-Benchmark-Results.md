# Surya Saarthi v2 — Benchmark results

| | |
|---|---|
| Generated | 27 Sep 2026, `python benchmark.py --ai-days 1` (from `backend`), seed 1 |
| Raw data | `backend/sample_results/benchmark.json` |
| Site (simulated) | 10 kW solar, 10 kWh battery (starts at 60%, 20% reserve, 92% round trip), 5 kW diesel genset, Delhi |
| Weather | Recorded: four one-week windows (Jan, May, Jul, Sep 2026). Actual = Open-Meteo ERA5 reanalysis; forecast = the day-ahead forecast actually issued (Open-Meteo Previous Runs API). Weather data by Open-Meteo.com (CC BY 4.0) |
| Demand | Simulated daily profile (home / small campus) + water pump and EV jobs; same for every controller |
| Power cuts | "Evening cuts" = an **illustrative** schedule, 19:00–22:00 every day, known in advance (e.g. from an operator note) |
| Costs | Grid import − export credit + battery wear + diesel. **Adjusted cost** also values battery energy left at the end, so no controller gains by emptying the battery |

**These are simulation results with stated assumptions (see README), not field measurements.** Battery price, cycle life, genset fuel use and diesel price are placeholders to replace with real quotes.

## Headline

| Condition | Fixed rule (Rs, 4 weeks) | Optimizer (Rs) | Lower cost | Per season | Diesel | CO₂ |
|---|---|---|---|---|---|---|
| Grid normal | 12,049 | 10,845 | **10.0%** (Rs 43/day) | 7.3% winter · 11.5% summer · 11.1% monsoon · 10.7% post-monsoon | 0 / 0 L | 832 → 798 kg |
| Daily 19–22 power cut | 17,797 | 13,176 | **26.0%** (Rs 165/day) | 25–27% in every season | **97.5 → 36.7 L** | 899 → 823 kg |

- **Zero** safety-rule overrides of the optimizer's plans in 1,344 simulated hours; **zero** essential load unserved for either controller.
- **Forecast quality is not the bottleneck:** the same optimizer given the *actual* weather as its forecast ("perfect") costs the same to within 0.1%. (It is not a true optimum: each hourly plan sees only 24 h, which is why it is occasionally a hair worse.)
- **Forecast correction does not help overall:** next-hour solar forecast error (MAE, daylight) raw → corrected: winter 0.070 → 0.083 kW, summer 0.284 → 0.316, monsoon 0.301 → 0.313, post-monsoon 0.235 → 0.216. It stays switched off (`config.FORECAST_CORRECTION`).

## AI (LLM) sample — one day only

Post-monsoon week, first day, 48 real Groq calls (`openai/gpt-oss-20b`), 0 AI-fallback hours. **A one-day sample; the LLM's answers also vary between runs.**

| Condition | Fixed rule | AI (LLM) decides | Optimizer |
|---|---|---|---|
| Grid normal, adjusted cost | Rs 417 | Rs 300 (9 hours needed a safety override) | **Rs 269** (0 overrides) |
| With the evening cut, adjusted cost | Rs 612 (3.3 L diesel) | Rs 433 (2.6 L; 8 override hours) | **Rs 336** (1.1 L; 0 overrides) |

Reading: the AI beats the fixed rule, but the optimizer beats the AI and never needs correcting. That is why v2 lets the optimizer decide and uses the AI for language (operator notes), with the AI mode kept for comparison.

## Full tables

## grid normal (7 days per season, seed 1)

| season | controller | adjusted cost Rs | net cost Rs | grid kWh | diesel L | unserved kWh | battery out kWh | CO2 kg | overrides | AI fallback h |
|---|---|---|---|---|---|---|---|---|---|---|
| winter | fixed | 3419.58 | 3403.9 | 375.1 | 0.0 | 0.0 | 57.4 | 258.31 | 0 | 0 |
| winter | optimizer | 3171.49 | 3156.38 | 372.24 | 0.0 | 0.0 | 57.26 | 256.28 | 0 | 0 |
| winter | optimizer+correct | 3171.49 | 3156.38 | 372.24 | 0.0 | 0.0 | 57.26 | 256.28 | 0 | 0 |
| winter | perfect | 3171.49 | 3156.38 | 372.24 | 0.0 | 0.0 | 57.26 | 256.28 | 0 | 0 |
| summer | fixed | 2760.8 | 2745.12 | 313.11 | 0.0 | 0.0 | 57.53 | 176.39 | 0 | 0 |
| summer | optimizer | 2444.49 | 2429.38 | 298.37 | 0.0 | 0.0 | 57.26 | 165.82 | 0 | 0 |
| summer | optimizer+correct | 2444.46 | 2429.35 | 298.32 | 0.0 | 0.0 | 57.31 | 165.83 | 0 | 0 |
| summer | perfect | 2444.43 | 2429.32 | 298.29 | 0.0 | 0.0 | 57.34 | 165.83 | 0 | 0 |
| monsoon | fixed | 2883.04 | 2867.35 | 326.5 | 0.0 | 0.0 | 55.86 | 192.31 | 0 | 0 |
| monsoon | optimizer | 2562.9 | 2547.58 | 311.59 | 0.0 | 0.0 | 55.77 | 181.73 | 0 | 0 |
| monsoon | optimizer+correct | 2562.86 | 2547.54 | 311.59 | 0.0 | 0.0 | 55.77 | 181.72 | 0 | 0 |
| monsoon | perfect | 2566.08 | 2558.94 | 313.59 | 0.0 | 0.0 | 53.77 | 183.14 | 0 | 0 |
| post-monsoon | fixed | 2986.07 | 2970.39 | 334.0 | 0.0 | 0.0 | 57.53 | 204.64 | 0 | 0 |
| post-monsoon | optimizer | 2665.76 | 2650.65 | 319.38 | 0.0 | 0.0 | 57.15 | 194.09 | 0 | 0 |
| post-monsoon | optimizer+correct | 2665.78 | 2650.67 | 319.39 | 0.0 | 0.0 | 57.14 | 194.09 | 0 | 0 |
| post-monsoon | perfect | 2665.42 | 2650.31 | 319.14 | 0.0 | 0.0 | 57.39 | 194.09 | 0 | 0 |
| post-monsoon | ai (1 d) | 299.61 | 283.91 | 31.93 | 0.0 | 0.0 | 11.51 | 16.82 | 9 | 0 |
| post-monsoon | fixed (1 d) | 417.22 | 401.52 | 43.93 | 0.0 | 0.0 | 11.51 | 25.34 | 0 | 0 |
| post-monsoon | optimizer (1 d) | 268.8 | 253.65 | 29.06 | 0.0 | 0.0 | 11.38 | 14.79 | 0 | 0 |

## evening cuts (7 days per season, seed 1)

| season | controller | adjusted cost Rs | net cost Rs | grid kWh | diesel L | unserved kWh | battery out kWh | CO2 kg | overrides | AI fallback h |
|---|---|---|---|---|---|---|---|---|---|---|
| winter | fixed | 5019.85 | 5004.17 | 299.64 | 26.95 | 0.0 | 57.4 | 276.96 | 0 | 0 |
| winter | optimizer | 3756.99 | 3741.88 | 346.47 | 9.21 | 0.0 | 57.26 | 262.65 | 0 | 0 |
| winter | optimizer+correct | 3756.99 | 3741.88 | 346.47 | 9.21 | 0.0 | 57.26 | 262.65 | 0 | 0 |
| winter | perfect | 3756.99 | 3741.88 | 346.47 | 9.21 | 0.0 | 57.26 | 262.65 | 0 | 0 |
| summer | fixed | 4114.03 | 4098.35 | 248.61 | 23.04 | 0.0 | 57.53 | 192.33 | 0 | 0 |
| summer | optimizer | 3015.84 | 3000.73 | 273.27 | 8.98 | 0.0 | 57.22 | 172.03 | 0 | 0 |
| summer | optimizer+correct | 3015.76 | 3000.65 | 273.21 | 8.98 | 0.0 | 57.28 | 172.03 | 0 | 0 |
| summer | perfect | 3015.77 | 3000.66 | 273.19 | 8.98 | 0.0 | 57.3 | 172.04 | 0 | 0 |
| monsoon | fixed | 4257.19 | 4241.5 | 261.07 | 23.37 | 0.0 | 55.86 | 208.48 | 0 | 0 |
| monsoon | optimizer | 3155.0 | 3139.89 | 285.58 | 9.31 | 0.0 | 55.72 | 188.21 | 0 | 0 |
| monsoon | optimizer+correct | 3155.16 | 3140.05 | 285.85 | 9.31 | 0.0 | 55.45 | 188.18 | 0 | 0 |
| monsoon | perfect | 3154.98 | 3139.87 | 285.62 | 9.31 | 0.0 | 55.68 | 188.2 | 0 | 0 |
| post-monsoon | fixed | 4405.57 | 4389.89 | 266.56 | 24.09 | 0.0 | 57.53 | 221.31 | 0 | 0 |
| post-monsoon | optimizer | 3248.18 | 3233.07 | 293.72 | 9.16 | 0.0 | 57.17 | 200.42 | 0 | 0 |
| post-monsoon | optimizer+correct | 3248.2 | 3233.09 | 293.74 | 9.16 | 0.0 | 57.15 | 200.42 | 0 | 0 |
| post-monsoon | perfect | 3248.0 | 3232.89 | 293.54 | 9.16 | 0.0 | 57.35 | 200.43 | 0 | 0 |
| post-monsoon | ai (1 d) | 433.34 | 417.64 | 21.72 | 2.58 | 0.0 | 11.51 | 16.47 | 8 | 0 |
| post-monsoon | fixed (1 d) | 611.57 | 595.87 | 34.67 | 3.31 | 0.0 | 11.51 | 27.63 | 0 | 0 |
| post-monsoon | optimizer (1 d) | 336.21 | 321.06 | 26.07 | 1.07 | 0.0 | 11.38 | 15.53 | 0 | 0 |

Next-hour solar forecast error (MAE, kW, daylight): {'winter': {'raw': 0.07, 'corrected': 0.083}, 'summer': {'raw': 0.284, 'corrected': 0.316}, 'monsoon': {'raw': 0.301, 'corrected': 0.313}, 'post-monsoon': {'raw': 0.235, 'corrected': 0.216}}
