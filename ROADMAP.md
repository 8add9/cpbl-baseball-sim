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

**Status:** In Progress — Web deployment architecture migration (2026-08-12)

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

**Status:** Complete for Phase 1 text product (2026-08-15)

The former create-player + Next-PA loop is migration code and no longer satisfies
acceptance. Completed v0.4 slice: five archetypes, weekly AP, skill XP/diminishing
returns, fatigue/recovery, formal UI concept, and shared-engine approach adapter.
The shipped v4 product loop is dashboard-first: weekly calendar/AP planning, skill XP,
fatigue/recovery, four scheduled games per week, season/career statistics, quick week
and season simulation, then mandatory season review, award, contract, offseason, and
next-season phases. The former Next-PA-first screen is no longer exposed by the Web UI.

Acceptance:

- Archetype creation, age, experience, development points, ratings, season/career stats, diminishing-return progression, local save/load, and simulation controls pass regression tests.

Evidence:

- Four equal-total-Score archetypes create age-18 batters; Score is authoritative and
  Raw/Display ratings remain derived through `B_QuadraticTanh`.
- Participation-only XP, a CPBL-informed conservative age curve, convex development
  costs, per-season/per-ability limits, potential ceilings, and a 20-season retirement
  boundary pass deterministic golden tests.
- Career games reuse the complete M3 nine-inning state. Every internal PA, inning/base/
  score state, partial active game, completed game, training action, season transition,
  and retirement replays from a versioned event stream. SpeedProxy remains visible and
  read-only until a researched runner model gives it a material effect.
- Next PA advances through intervening neutral-fixture batters to the created player's
  next appearance. Next important event stops at the first DP threshold, completed game,
  or completed-season boundary, so it is distinct from the single-appearance control.
- SQLite autosave uses transactions, optimistic revisions, and idempotent operation IDs;
  create → simulate → train → API restart → load retained revision, games, and Power.
- Browser QA covered identity creation, next PA, partial-save API restart, quick game,
  six-game week, training, next event, and responsive layouts. Python: 100 passed/1
  opt-in SQL test skipped. Frontend: 3 tests,
  ESLint, TypeScript/Vite build, and npm audit all pass.

## M6 — Manager Mode 1-2

**Status:** Complete (2026-08-12)

Acceptance:

- Player-season cards, researched tiers/costs, roster building, lineup, rotation/bullpen, substitutions, games, standings, and roster constraint QA work.
- Optimization simulations demonstrate viable non-all-star roster strategies.

Current evidence:

- `rating-snapshot-v0.2` exports 3,035 batter cards, 2,125 pitcher cards, and
  2,138 normalized player profiles through the SELECT-only source identity.
- The fail-closed catalog loads 5,160 cards, excludes 159 incomplete 2026 cards from
  competitive tiers, and reproduces the researched batter/pitcher tier counts.
- Pure roster validation covers 22 cards, budget 70, tier caps, distinct position
  coverage, four SP, five bullpen pitchers, and one season card per PlayerID.
- Exact-position lineup/bench state, PA-boundary pinch hitting and pitching changes,
  no-reentry rules, and role-specific Stamina BF capacity pass regression tests.
- The seeded six-team schedule produces 360 games, 120 per team, balanced home/away
  series, and deterministic PCT/GB/tie-break standings.
- Full Manager games now reuse the M3 PA engine with actual card Raw ratings, automatic
  BF-capacity pitching changes, deterministic replay/pause, and no neutral fallback.
- Cross-game usage enforces a four-SP rest cycle and blocks RP/Swingman cards from a
  third consecutive team game. Six legal, disjoint AI rosters can complete all 360
  scheduled games with internally consistent standings.
- Deterministic beam-search roster builders produce balanced, offense-heavy,
  pitching-heavy, and zero-SSR fixtures under the same legality contract. Strategy
  regression tests require distinct card sets and directional batter/pitcher impact.
- The release balance run completed 120,000 games: six 20,000-game paired comparisons.
  All three zero-SSR strategies cleared the reference and mutual-balance gates; mutual
  gaps were 1.18-4.01 expected wins per 120 games.
- SQLite Manager saves preserve the catalog fingerprint, rosters, pitcher availability,
  schedule cursor, results, revisions, and compact idempotency metadata. FastAPI exposes
  create/load, roster candidates, preseason card replacement, and three simulation speeds.
- The responsive React dashboard supports multiple saves, real-card inspection,
  preseason roster replacement with server-side budget/tier/position/role validation,
  standings, rotation/bullpen status, and season simulation.
- Browser QA covered create, invalid star-card replacement, valid roster replacement,
  play one game, restart/load, four mobile tabs, desktop/mobile overflow, and console
  errors. Python: 181 passed/1 opt-in SQL test skipped. Frontend: 6 tests plus ESLint and
  production build.

## M7 — Phase 1 completion

**Status:** Complete for the requested Phase 1 text simulation scope (2026-08-15)

Acceptance:

- All prior gates pass together, persistent saves work, full browser playthrough passes, docs/screenshots/CI are current.
- A new GitHub repository is created, committed, pushed, and deployed to a working browser URL.
- GitHub Pages serves only the Vite static build and calls the authoritative Linux API
  through ngrok HTTPS configured by `VITE_API_BASE_URL`.
- FastAPI and SQL Server remain loopback-only; CORS permits the Pages origin rather than
  a wildcard.
- Health, game creation/action/reload, fast simulation, backend restart, ngrok URL update,
  offline handling, and server-authoritative outcome boundaries pass production checks.

Evidence:

- Public release repository: `https://github.com/8add9/cpbl-baseball-sim`.
- GitHub Pages: `https://8add9.github.io/cpbl-baseball-sim/`; deployment run
  `31554162283` passed. Architecture/CI run `31554028697` also passed.
- The Linux API is exposed through the configured ngrok HTTPS endpoint while FastAPI
  binds only to `127.0.0.1:8000`; SQL Server remains on `127.0.0.1:1433` and CORS allows
  only the Pages origin.
- The previous same-origin LAN container deployment is retained only as migration
  evidence. It does not satisfy the new GitHub Pages + ngrok completion gate.
- Deployment smoke tests returned UI 200 and game creation 201; Manager loaded the
  hash-pinned 5,160-card catalog and created six teams/132 cards. After a real container
  restart, both Career and Manager saves reloaded at their original revisions.
- Production Pages browser QA passed health, game creation, Next PA, reload recovery and
  half-inning simulation with no console warnings or errors. The SQL Server source
  container remained separate and unchanged.

The Pages/ngrok path is operational. Career and Manager have durable SQLite adapters;
local restart-replay and a two-complete-season Career API acceptance pass. The standalone
ordinary text-game homepage was removed; Manager is now the default entry. Phase 2
remains blocked regardless.

## Phase 2 — Operable batting prototype

Out of the current scope by user direction. Stop after M7; do not begin the
全民打棒球-style prototype in this delivery.
