# Known Issues

## Station-to-station runner advancement

The v0.1 game state advances every runner exactly the hit's base value and holds all runners on outs. It cannot represent sacrifice flies, double plays, errors, fielder's choices, first-to-third, scoring from second on a single, wild pitches, passed balls, SpeedProxy, Fielding, or Arm. Full-game scoring and LOB distributions are therefore provisional even though state transitions are deterministic and legal.

`station-to-station-v0.1` is stored as a rules version so future empirical advancement logic does not silently alter old saves or replays.

## Text Game fixture

The Text Game currently uses neutral 65-vs-65 fixture cards (`A1`–`A9`, `H1`–`H9`) to prove the end-to-end game workflow. Real CPBL card selection is deferred to the roster/Manager milestone. Text Game sessions remain in memory; Career saves are separately persistent and schema-versioned.

## Open

- The first hierarchical PA probability model is accepted for v0.1, but its extreme
  Power tail remains provisional until the scheduled saturating-tail comparison.
- Historical park, opponent, defense, catcher framing, and pitch-level context are unavailable or incomplete.
- Stuff, HRSuppression, SpeedProxy, and Stamina are explicitly proxies.
- Pitcher B_Role extreme tails are dominated by Swingman seasons; role-tail sensitivity remains a monitoring item.
- 2026 is incomplete and must not enter historical baselines.
- Overall ratings are not calibrated for the 30–110 scale and are excluded from v0.1 single-skill simulation inputs.
- Career persistence is local SQLite. Deployment persistence and the Manager game-data
  store remain undecided until hosting requirements are measured.
- SpeedProxy is visible but read-only in Career Mode because it has no PA or runner
  effect; training unlocks only after an empirical runner model exists.
- `ProfilePosition`, Bats, and Throws are static player profiles rather than season-level
  histories. LF/CF/RF may satisfy the OF roster family, but Fielding and multi-position
  eligibility remain unmodeled. Transfer-card Team values are aggregated display labels,
  not a canonical single TeamID.
- A Manager game normally forces a pitching change after the active pitcher's
  Stamina-derived BF limit. If every unused and cross-game-available bullpen card has
  already been exhausted, the current real pitcher continues under an explicit
  `bullpen-exhausted-extension` event. This prevents a legal extra-inning game from
  deadlocking and never invents a neutral pitcher, but it is not a claim that fatigue
  disappears; deeper staffs and fatigue-quality effects require a future model version.
- Manager tier/cost policy has not passed its final 20,000-paired-game balance gate yet.
  Early fixed-seed samples place zero-SSR strategies near the intended competitive
  boundary, but they are not sufficient evidence to freeze costs or declare M6 complete.
- Career save schemas v1-v2 are intentionally rejected by the v3 full-GameState loader;
  no public saves existed before the milestone, so a migration was not retained.
- `B_QuadraticTanh` is mathematically monotonic for finite real scores, but double precision loses strict distinguishability extremely near the 30/110 asymptotes. Engine validation guarantees round-trip behavior for the supported score domain `[-10, 10]`; endpoints remain display-only labels.
- The crawler/research project still owns an administrative credential, but the game project now uses `baseball_game_reader`; SELECT succeeds and an attempted zero-row UPDATE is denied. Keep the admin credential out of this repository.
- Public deployment rights for CPBL-derived data, player names, team names, trademarks, and logos require review before release; early UI should use text and original visual assets.

## Blockers

None currently. Ordinary implementation and calibration work remains.
