# Roadmap

## M0 — Foundation and audit

**Status:** Complete (2026-08-11)

Acceptance:

- Existing rating research and SQL connection rerun successfully.
- Governance documents and project-local balance skill exist and validate.
- Phase 1 architecture and immutable data boundary are documented.
- First probability/property test skeletons exist and run.

Evidence:

- All four source research pipelines reran successfully against live SQL.
- Teams/Players/BattingStats/PitchingStats remained `17/2138/4190/3468`; independent checksum audit also matched before/after.
- Dedicated `baseball_game_reader` can SELECT and is denied UPDATE, INSERT, and DELETE on `dbo`.
- Project-local skill validation passed.
- Locked `uv` environment passed 19 pytest cases, Ruff, and strict mypy on Windows Python 3.12 and Linux Python 3.14.
- Independent local Git history established without creating a GitHub remote.

## M1 — Rating Engine v0.1

**Status:** Complete (2026-08-11)

Acceptance:

- Read-only source adapter produces versioned batter and pitcher player-season records with required scores, raw/display ratings, role, confidence, incomplete flag, and as-of date.
- Schema validation, deterministic regeneration, row-count reconciliation, and golden-card fixtures pass.
- No source SQL rows or raw statistics change.

Evidence:

- Deterministic exports produced 3,035 batter cards and 2,125 pitcher cards twice with identical SHA-256 hashes.
- Manifest fingerprints all four SQL source tables under `baseball_game_reader` and records schema, engine, model, mapping, as-of, inputs, outputs, and invariants.
- Cards preserve Score, RatingRaw, RatingDisplay, role/confidence/incomplete metadata and exclude uncalibrated Overall.
- Live integration fixture reconciles 2014 高國輝 Power and 1998 賈西 Stuff to the approved research values.
- 2026 cards are incomplete; completed seasons are not. SQL reader has no UPDATE permission.

## M2 — Matchup model and CLI checkpoint

**Status:** In progress

Acceptance:

- At least log-odds, multiplicative-odds, and hierarchical candidates are compared against historical league baselines.
- CLI supports explicit ratings, PA count, and seed.
- Every relevant rating passes direction, effect-size, bounds, and monotonicity tests.
- Golden and interaction matchups run at least 100,000 PA with reproducible reports.
- Power 100 versus 65 materially increases HR, ISO/SLG, and extra-base damage under controlled inputs.

## M3 — Baseball game state machine

Acceptance:

- Nine innings, half innings, three outs, bases, score, lineup order, pitchers, PA outcomes, runner advancement, and extra innings work.
- Unit/property tests cover scoring, base states, inning transitions, walk-offs, and deterministic replay.

## M4 — Text Game web MVP

Acceptance:

- FastAPI server and React client support next PA, half-inning sim, full-game sim, reset, deterministic seed, live situation, ratings, play log, and box score.
- Responsive browser QA passes; UI is product-quality, not a debug panel.

## M5 — Career Mode 1-1

Acceptance:

- Archetype creation, age, experience, development points, ratings, season/career stats, diminishing-return progression, local save/load, and simulation controls pass regression tests.

## M6 — Manager Mode 1-2

Acceptance:

- Player-season cards, researched tiers/costs, roster building, lineup, rotation/bullpen, substitutions, games, standings, and roster constraint QA work.
- Optimization simulations demonstrate viable non-all-star roster strategies.

## M7 — Phase 1 completion

Acceptance:

- All prior gates pass together, persistent saves work, full browser playthrough passes, docs/screenshots/CI are current.
- A new GitHub repository is created, committed, pushed, and deployed to a working browser URL.

## Phase 2 — Operable batting prototype

Begins only after M7. Deliver one polished field, pitcher, batter, pitch, and swing with timing/aiming effects consistent with the Phase 1 rating model.
