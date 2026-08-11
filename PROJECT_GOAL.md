# Project Goal

Build and deploy a playable CPBL-derived baseball game from the immutable historical data and validated rating research in `/home/chester/baseball-data`.

## Product completion

The long-term goal is complete only when:

- Phase 1 is a deployed, browser-playable numerical baseball game with Rating Engine, validated matchup simulation, game state machine, Text Game, Career Mode, Manager Mode, persistent saves, automated tests, and browser QA.
- Phase 2 is a playable 2D/2.5D pitcher-versus-batter prototype where human timing and aiming modify, but do not replace, the Phase 1 matchup model.
- Documentation, CI, GitHub publication, and deployment are verified.

## Current checkpoint

Milestone 0: Foundation and evidence audit.

Next product checkpoint: a deterministic CLI Monte Carlo batter-versus-pitcher simulator that runs 100,000 PA and demonstrates a material, statistically stable Power 100 versus Power 65 difference while holding all other ratings constant.

Career Mode and Manager Mode are prohibited until the CLI matchup checkpoint passes.

## Immutable constraints

- `BaseballRealData` is a read-only truth source for game development.
- Game ratings, simulations, saves, and progression live outside raw historical tables.
- Batter model is `A_WinsorizedBalanced`; pitcher model is `B_Role`.
- Both use `B_QuadraticTanh`; simulations use raw scores/ratings, never rounded display ratings.
- 2026 remains incomplete as of 2026-08-11 and is excluded from historical calibration baselines.
