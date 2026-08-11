# Known Issues

## Station-to-station runner advancement

The v0.1 game state advances every runner exactly the hit's base value and holds all runners on outs. It cannot represent sacrifice flies, double plays, errors, fielder's choices, first-to-third, scoring from second on a single, wild pitches, passed balls, SpeedProxy, Fielding, or Arm. Full-game scoring and LOB distributions are therefore provisional even though state transitions are deterministic and legal.

`station-to-station-v0.1` is stored as a rules version so future empirical advancement logic does not silently alter old saves or replays.

## M4 web fixture and persistence

The Text Game currently uses neutral 65-vs-65 fixture cards (`A1`–`A9`, `H1`–`H9`) to prove the end-to-end game workflow. Real CPBL card selection is deferred to the roster/Manager milestone. FastAPI sessions are in memory and disappear on process restart; persistent, schema-versioned saves are a Career milestone gate.

## Open

- The first PA probability model and its coefficients are not yet accepted.
- Historical park, opponent, defense, catcher framing, and pitch-level context are unavailable or incomplete.
- Stuff, HRSuppression, SpeedProxy, and Stamina are explicitly proxies.
- Pitcher B_Role extreme tails are dominated by Swingman seasons; role-tail sensitivity remains a monitoring item.
- 2026 is incomplete and must not enter historical baselines.
- Overall ratings are not calibrated for the 30–110 scale and are excluded from v0.1 single-skill simulation inputs.
- Game persistence technology and deployment provider remain undecided until API/runtime requirements are measured.
- `B_QuadraticTanh` is mathematically monotonic for finite real scores, but double precision loses strict distinguishability extremely near the 30/110 asymptotes. Engine validation guarantees round-trip behavior for the supported score domain `[-10, 10]`; endpoints remain display-only labels.
- The crawler/research project still owns an administrative credential, but the game project now uses `baseball_game_reader`; SELECT succeeds and an attempted zero-row UPDATE is denied. Keep the admin credential out of this repository.
- Public deployment rights for CPBL-derived data, player names, team names, trademarks, and logos require review before release; early UI should use text and original visual assets.

## Blockers

None currently. Ordinary implementation and calibration work remains.
