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

**Status:** Complete (2026-08-11)

Acceptance:

- At least log-odds, multiplicative-odds, and hierarchical candidates are compared against historical league baselines.
- CLI supports explicit ratings, PA count, and seed.
- Every relevant rating passes direction, effect-size, bounds, and monotonicity tests.
- Golden and interaction matchups run at least 100,000 PA with reproducible reports.
- Power 100 versus 65 materially increases HR, ISO/SLG, and extra-base damage under controlled inputs.

Evidence:

- Three candidates ran against the audited 2021-2025 baseline; hierarchical was accepted because Power has zero structural leakage into BB/HBP/SO while flat and naive normalization do not.
- Nine grouped-binomial slopes were estimated from 2,940 eligible batter seasons and 2,061 eligible pitcher seasons; every 95% interval excluded zero.
- Fixed-seed 100,000-PA Power 65 vs 100 produced +7,976 HR and +.349 simulated SLG; analytic deltas were +7.855 HR percentage points and +.342 SLG.
- 33 tests pass, including probability, monotonicity, conditional-isolation, deterministic sampler, interaction, and Monte Carlo checkpoint tests.
- Tail strength is explicitly provisional: linear log-odds will be compared with a monotone saturating sensitivity before balance freeze.

## M3 — Baseball game state machine

**Status:** Complete (2026-08-11)

Acceptance:

- Nine innings, half innings, three outs, bases, score, lineup order, pitchers, PA outcomes, runner advancement, and extra innings work.
- Unit/property tests cover scoring, base states, inning transitions, walk-offs, and deterministic replay.

Evidence:

- Immutable pure-domain transitions implement all eight PA outcomes, forced walks, explicit station-to-station advancement, nine-player lineups, active pitchers, regulation endings, walk-offs, and unlimited extras.
- Counter-based BLAKE2b draws key on seed, PA index, channel, and model version; a save resumed after 25 PA exactly matches uninterrupted outcomes and final state.
- Non-HR walk-offs credit only the runs required to win; walk-off home runs credit all runners and batter.
- 55 tests pass, including arbitrary outcome-stream properties and complete-game replay fixtures.
- 1,000 fixed-seed neutral games all reached legal finals; mean 81.85 PA, 15.3% extras, longest 24 innings. These are rule-validation figures, not a claim of calibrated CPBL scoring.

## M4 — Text Game web MVP

**Status:** Complete (2026-08-12)

Acceptance:

- FastAPI server and React client support next PA, half-inning sim, full-game sim, reset, deterministic seed, live situation, ratings, play log, and box score.
- Responsive browser QA passes; UI is product-quality, not a debug panel.

Evidence:

- FastAPI exposes create/read/next-PA/simulate-half/simulate-full/reset with explicit Pydantic contracts, structured 404/409/422 errors, rollback on safety-limit failures, and thread-safe isolated session snapshots.
- React/Vite implements the accepted desktop/mobile scorebook concept with code-native score, base state, six supported ratings, play log, lineups, controls, loading/error/final states, and no unsupported Fielding/Arm values.
- Browser QA verified load → next PA → half inning → full game → reset. Final games disable simulation; reset restores the same fixed seed; console contained no errors or warnings.
- Desktop 1440×1000 and mobile 390×844 had no horizontal document overflow. Mobile reset was moved into the header after visual review.
- Python: 64 passed/1 opt-in SQL integration skipped. Frontend: ESLint, Vitest, TypeScript production build, and npm audit (0 vulnerabilities) pass.

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
