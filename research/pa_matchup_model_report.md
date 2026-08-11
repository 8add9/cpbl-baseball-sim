# PA Matchup Model Research v0.1

## Decision

Accept the hierarchical model for the first playable numerical prototype. 
The flat log-odds and naive multiplicative models remain explicit comparators.

## Candidate comparison: Power 65 -> 100

| Model | HR% 65 | HR% 100 | HR pp delta | SLG 65 | SLG 100 | SLG delta | BB pp leakage | K pp leakage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| hierarchical | 1.337 | 9.192 | 7.855 | 0.350 | 0.693 | 0.342 | 0.000 | 0.000 |
| flat-log-odds | 1.337 | 9.139 | 7.802 | 0.350 | 0.727 | 0.377 | -0.848 | -1.938 |
| naive-multiplicative | 1.337 | 3.859 | 2.522 | 0.350 | 0.501 | 0.151 | -0.386 | -0.881 |

Hierarchical wins the semantic gate because Power leaves the earlier BB, HBP and SO conditional stages exactly unchanged. Flat and naive renormalization change unrelated absolute outcomes.

## Calibration evidence

Grouped-binomial slopes use 2,940 completed batter seasons (PA>=50) and 2,061 completed eligible pitcher seasons. Intentional walks are excluded. Every reported 95% interval excludes zero; the full coefficient table is written to `artifacts/research/pa_model_coefficients.csv`.

## First hard checkpoint

- Fixed seed: `20260811`; PA per side: `100,000`.
- Analytic HR-rate delta: `0.078546`.
- Analytic SLG delta: `0.342428`.
- Simulated HR-count delta: `7976`.
- Simulated SLG delta: `0.348808`.
- This is a 2021-2025 league-neutral counterfactual. Rating 65 is anchored to the chosen league environment by product convention; it is not a claim that historical Score-0 players exactly equal the PA-weighted league rate.

The checkpoint passes when HR-rate increases by at least 0.5 percentage points and SLG by at least 0.050 analytically, with the fixed 100k sample confirming the direction and material size.

## Limitations

This is a season-card matchup approximation, not independently identified batter-vs-pitcher interaction research. SpeedProxy and Stamina intentionally do not affect one-PA quality. Intentional walks and game state are deferred. Coefficients remain versioned and must be replaced only through calibration evidence, never named-player exceptions.
Power-to-HR slopes remain about 0.39-0.43 by decade, but the linear Score tail must still be compared with a monotone saturating alternative before balance freeze.
