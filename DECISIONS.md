# Decisions

## ADR-001 — Separate game repository

- **Decision:** Develop the game in `cpbl-baseball-sim`, separate from `baseball-data`.
- **Why:** Historical data is immutable infrastructure; game code, derived ratings, saves, and balance iterations have different lifecycles.
- **Alternatives:** Add game packages to the data repository; wait until MVP before creating any separate project.
- **Consequences:** A source adapter and artifact contract are required. The data project remains untouched. GitHub publication waits for the MVP gate.
- **Date:** 2026-08-11

## ADR-002 — Pure Python authoritative domain

- **Decision:** Use a pure Python domain package, FastAPI adapter, and React/TypeScript client.
- **Why:** Existing rating research is Python; pure domain code supports CLI, Monte Carlo, API, and tests without UI coupling.
- **Alternatives:** TypeScript-only simulation; client-authoritative prototype; monolithic web framework.
- **Consequences:** Frontend cannot decide outcomes. Serialization contracts and separate API tests are required.
- **Date:** 2026-08-11

## ADR-003 — Hierarchical PA outcome research

- **Decision:** Compare multiple candidates, with hierarchical probability decomposition as the leading architecture rather than a single linear rating difference.
- **Why:** BB, SO, balls in play, and hit types require bounded conditional probabilities and interpretable rating effects.
- **Alternatives:** Direct multiclass softmax; simple rating subtraction; independent Bernoulli draws.
- **Consequences:** Calibration requires league baseline events, normalization, probability properties, and interaction tests.
- **Date:** 2026-08-11

## ADR-004 — Preserve raw and display ratings

- **Decision:** Persist score, full-precision RatingRaw, and rounded RatingDisplay; rank and simulate with raw values only.
- **Why:** Integer display creates ties and loses information.
- **Alternatives:** Store only integers; simulate directly from labels.
- **Consequences:** Contracts and UI must carry both representations.
- **Date:** 2026-08-11

## ADR-005 — Supported floating-point rating domain

- **Decision:** Guarantee inverse round-trip and strict floating-point ordering for final scores in `[-10, 10]`; treat 30 and 110 as non-invertible display asymptotes.
- **Why:** IEEE-754 values become indistinguishable extremely close to a tanh asymptote, while all observed research scores are comfortably inside this domain.
- **Alternatives:** Pretend all finite floats are strictly distinguishable; clip to30/110; use arbitrary-precision arithmetic at runtime.
- **Consequences:** Input validation and property tests use the supported domain. Raw ratings must be in the open interval `(30,110)`.
- **Date:** 2026-08-11

## ADR-006 — Versioned rating snapshots

- **Decision:** Generate versioned batter and pitcher rating snapshots, normalized
  player-profile metadata, and a manifest; do not query raw SQL during gameplay.
- **Why:** Games must be reproducible, deployable, and isolated from changing research artifacts.
- **Alternatives:** Import research scripts at runtime; query `BaseballRealData` for every game action.
- **Consequences:** M1 requires an importer, source fingerprint, deterministic artifact
  hashes, and model/mapping/profile metadata. `ProfilePosition` is a player-level primary
  position proxy, not a season-specific defensive rating.
- **Date:** 2026-08-11

## ADR-007 — Read-only truth-source identity

- **Decision:** The game uses SQL login `baseball_game_reader` with data-reader membership and explicit DML denial on `dbo`.
- **Why:** Policy-only immutability under `sa/dbo` is insufficient.
- **Alternatives:** Continue using the research credential; copy raw tables into the game database.
- **Consequences:** Secrets remain untracked, integration tests must prove SELECT works and UPDATE fails, and rating artifacts remain outside raw tables.
- **Date:** 2026-08-11

## ADR-008 — Current completed-season baseline

- **Decision:** Use PA-weighted 2021–2025 CPBL outcomes excluding intentional walks as the default v0.1 environment; allow explicit historical environments later.
- **Why:** It represents current completed seasons without allowing incomplete 2026 data to calibrate gameplay.
- **Alternatives:** Pool 1990–2025; use 2025 only; average player-season rates.
- **Consequences:** The baseline and source counts are versioned. Era selection becomes an explicit context rather than a hidden model shift.
- **Date:** 2026-08-11

## ADR-009 — Hierarchical PA model v0.1

- **Decision:** Accept a four-way BB/HBP/SO/contact softmax followed by conditional HR, hit/out, and hit-type stages. Use empirically estimated 1990-2025 Score-scale slopes.
- **Why:** It preserves total probability and keeps Power/HRSuppression out of earlier BB/HBP/SO equations. The flat comparator leaked roughly -0.85 BB and -1.94 K percentage points when only Power moved 65 to 100.
- **Alternatives:** Flat multinomial log-odds; clipped linear multiplicative weights.
- **Consequences:** Rating 65 versus 65 is anchored to the selected league environment by convention. The Score tail is not frozen; M3 balance QA must compare a monotone saturating tail because Power 100 is an extreme Score 4.96 counterfactual.
- **Date:** 2026-08-11

## ADR-010 — Versioned state transitions and counter-based draws

- **Decision:** Keep `apply_outcome` pure and sample PA outcomes with a BLAKE2b draw keyed by seed, PA index, draw channel, and simulation-model version. Use explicit `station-to-station-v0.1` advancement rules.
- **Why:** Saves need only state plus counters, new random channels cannot perturb existing PA sequences, and event replay remains independent from an RNG library's mutable internal state.
- **Alternatives:** Persist NumPy RNG state; call global random state; sample runner advancement inside the transition function.
- **Consequences:** Model/rules versions are part of every game save. The simplified advancement model is auditable but full-game scoring remains provisional until empirical runner transitions are available.
- **Date:** 2026-08-11

## ADR-011 — Score-authoritative Career progression

- **Decision:** Career training purchases Composite Score steps, never direct Rating
  points. Archetypes begin with equal total Score and use convex cost, per-season limits,
  potential ceilings, deterministic age drift, and a twenty-season boundary.
- **Why:** The mapping already supplies diminishing rating returns, while Score keeps
  simulation semantics stable and prevents integer-display optimization. Participation XP
  avoids rewarding strong outcomes with still faster growth.
- **Alternatives:** Add one Rating per game; performance-based XP; free starting sliders.
- **Consequences:** SpeedProxy is persisted but read-only until runner research gives it
  a tested material effect. Progression changes require a model-version migration.
- **Date:** 2026-08-12

## ADR-012 — Revisioned local Career saves

- **Decision:** Persist Career event/state payloads in a separate SQLite database with
  full transactions, optimistic revisions, and an idempotent operation ledger.
- **Why:** Process-local locks and browser localStorage cannot safely cover API restarts,
  retry duplication, or stale multi-tab writes.
- **Alternatives:** Reuse BaseballRealData; unversioned JSON files; client-only storage.
- **Consequences:** The API accepts server UUIDs rather than file paths. Corrupt or future
  saves fail closed. Public deployment still requires authentication and hosted storage.
- **Date:** 2026-08-12

## ADR-013 — Analytic card impact and budget tiers

- **Decision:** Price Manager cards from the accepted PA model against neutral-65
  opposition: batter simplified OPS and the negative of pitcher OPS allowed. Use
  completed-pool average-rank percentiles for N/R/SR/SSR at 40/75/95 percent and costs
  1/3/6/10 under policy `tier-impact-v0.1+baseline2021-25`.
- **Why:** This preserves researched component semantics, keeps Stamina in workload, and
  avoids inventing an Overall or averaging integer Display ratings.
- **Alternatives:** Mean ability display; historical reputation tiers; fixed per-ability
  thresholds; unrestricted all-star rosters.
- **Consequences:** 2026 cards are exhibition-only. Saves pin the catalog manifest hash.
  Tier labels mean budget impact rather than awards or collectible rarity, and the policy
  must pass paired non-all-star strategy simulations before M6 is complete.
- **Date:** 2026-08-12

## ADR-014 — Stamina controls workload, not PA quality

- **Decision:** Convert pitcher Stamina Raw into a role-specific hard batters-faced
  capacity. A pitcher completes the PA that reaches the limit and must be replaced before
  the next fielding PA; PA outcome probabilities remain unchanged.
- **Why:** Current research supports workload but not a fatigue-quality curve. Without a
  capacity, relievers can unrealistically start and finish every game.
- **Alternatives:** Ignore Stamina; reduce Stuff linearly while tired; use pitch counts
  that the source data cannot calibrate.
- **Consequences:** SP, Swingman, and RP use separate clamped formulas. Substitutions occur
  only at PA boundaries, and used batters or pitchers cannot re-enter in v0.1.
- **Date:** 2026-08-12

## ADR-015 — Deterministic six-team Manager season

- **Decision:** Use a seeded circle schedule with six teams, 24 games per opponent split
  12 home/12 away, for 120 games per team and 360 league games. Rank by PCT, run
  differential, runs scored, then TeamID; Manager games cannot end tied.
- **Why:** It supplies a reproducible league and standings contract without claiming to
  reproduce a particular CPBL calendar or official tie-break regulation.
- **Alternatives:** Copy one historical calendar; generate mutable random schedules;
  include rainouts and ties before those systems are modeled.
- **Consequences:** Schedule seed and rule version belong in Manager saves. Calendar dates,
  rainouts, and official CPBL postseason rules remain deferred.
- **Date:** 2026-08-12

## ADR-016 — Real-card Manager game orchestration

- **Decision:** Run Manager games through the existing M3 PA engine using full-precision
  card ratings, a four-SP rotation, cross-game bullpen availability, and deterministic
  automatic pitching changes at PA boundaries.
- **Why:** Manager Mode must preserve the accepted matchup probabilities and replay
  contract while making Stamina, pitcher roles, rest, and roster depth materially affect
  a season.
- **Alternatives:** Create a faster second game simulator; allow relievers to start;
  ignore rest and workload; insert a neutral emergency pitcher.
- **Consequences:** Starters follow a four-game rotation with three intervening team
  games; RP/Swingman cards may work at most two consecutive team games. When a legal game
  exhausts every unused,
  available bullpen card, the current real pitcher is explicitly marked for
  `bullpen-exhausted-extension` and may exceed the BF capacity so extra-inning games can
  terminate without fabricating a neutral card. This safety exception is provisional
  and must be replaced by deeper roster/fatigue rules in a later model version.
- **Date:** 2026-08-12
