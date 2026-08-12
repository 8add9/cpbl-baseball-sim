# Manager Mode paired balance validation

Snapshot: `rating-snapshot-v0.2:6929d51c8ad6564ac99ac39c615076fabe8f07a187b669b7b8734532168b04ac`. Seed: `20260812`. Workers: `8`.
Each comparison used **20,000 games / 10,000 paired seeds**.

A pair reuses one random seed with home/away reversed. The 95% CI treats the pair score (0, 0.5, 1) as one independent observation. The release gate requires at least 20,000 games per comparison. A non-star roster must have a paired-CI lower bound of at least 45% and trail the legal reference by no more than eight expected wins per 120. Mutual non-star matchups must remain within 45%-55% or six wins per 120.

## Rosters

| Team | Strategy | Rule | Cost | SR | SSR |
|---|---|---:|---:|---:|---:|
| reference | balanced | standard-legal | 69 | 1 | 0 |
| balanced | balanced | 0SSR-3SR | 69 | 1 | 0 |
| offense | offense | 0SSR-3SR | 70 | 2 | 0 |
| pitching | pitching | 0SSR-3SR | 69 | 3 | 0 |

The four fixtures are deterministic and mutually card-disjoint. The reference is a standard legal balanced optimizer roster; the other three use 0 SSR / at most 3 SR.

## Results

| Comparison | Win rate | 95% paired CI | Wins/120 | R/G | Opp R/G | Gate |
|---|---:|---:|---:|---:|---:|---:|
| balanced_vs_reference | 52.610% | 52.009%–53.211% | 63.13 | 3.329 | 3.090 | PASS |
| offense_vs_reference | 55.035% | 54.432%–55.638% | 66.04 | 3.538 | 3.072 | PASS |
| pitching_vs_reference | 51.155% | 50.559%–51.751% | 61.39 | 3.088 | 2.978 | PASS |
| balanced_vs_offense | 47.825% | 47.222%–48.428% | 57.39 | 3.072 | 3.229 | PASS |
| balanced_vs_pitching | 50.985% | 50.400%–51.570% | 61.18 | 2.940 | 2.857 | PASS |
| offense_vs_pitching | 53.345% | 52.759%–53.931% | 64.01 | 3.123 | 2.853 | PASS |

## Decision

**Release balance gate passed.**
Failures are reported as measured; this research harness does not alter card costs, optimizer weights, or game-engine coefficients.

## Interpretation limits

This isolates roster construction and single-game simulation. Every game starts with a fresh bullpen, so season fatigue/availability, injuries, and human lineup management are outside this gate. Starting pitchers rotate evenly across paired trials.
