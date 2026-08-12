# Career Mode v0.4

Career Mode is a weekly player-development game, not a plate-appearance clicker:

```text
create -> weekly plan -> train/recover/play -> player PA decisions -> post-game
-> events/week review -> season review -> awards/contract/offseason -> next season
```

The dashboard is centered on the seven-day schedule, four weekly Action Points,
condition, team status, Coach Trust, next game, and attainable season goals. `Next PA`
exists only inside an active player appearance; it is never the Career home action.

## Progression

Permanent ability remains Composite Score. `B_QuadraticTanh-v1` derives RatingRaw and
UI-only RatingDisplay. Potential is a development trait, not a hard cap. Skill XP carries
across weeks and an increasingly expensive threshold buys each `+0.1 Score`. Age,
potential, fatigue, repeated training and a soft development center affect efficiency.

Policy `career-weekly-v0.4` gives four AP. Focused Contact/Power/Eye costs two;
Speed/Recovery/Video/Extra BP costs one. Repeating a skill uses
`1.00/.70/.45/.30` efficiency while fatigue rises. Recovery reduces fatigue but never
changes permanent ratings. Speed remains a proxy and cannot claim SB impact before an
accepted runner model exists.

## Condition, status, and approaches

Fatigue `0..100` and mean-reverting Form `-2..2` modify effective game ratings only.
Coach Trust and team status combine ability, shrunk performance, discipline,
availability, position need, fatigue and hysteresis. The server decides Starter, Pinch
Hit, Pinch Run or DNP.

Normal, Aggressive, Patient, Power Swing, Contact and Situational are versioned inputs to
the accepted hierarchical PA engine, never a second outcome model. Normal at neutral
condition is bit-identical to ordinary gameplay. Other approaches adjust Score inputs,
so effects interact with player ability rather than add a fixed outcome percentage.

## Lifecycle and persistence

```text
WEEK_PLANNING -> DAY_READY -> PARTICIPATION -> PLAYER_PA_READY
-> BETWEEN_PLAYER_PA -> POST_GAME -> WEEK_REVIEW -> SEASON_REVIEW
-> AWARDS -> CONTRACT -> OFFSEASON_TRAINING -> READY_NEXT_SEASON | RETIRED
```

Only server-advertised actions are legal. All mutations use expected revision and an
idempotency operation ID. Linux stores the authoritative state; browser storage contains
only Career ID and UI preferences. Schema v4 must transactionally migrate v3 saves,
including active GameState and legacy training credit.

Existing outcomes reliably support G/PA/AB/H/1B/2B/3B/HR/BB/HBP/SO and slash lines.
R/RBI attribution, SB/CS and runner milestones require event metadata not yet present;
they may not be filled with fake zeros. Awards require a seeded league-stat cohort and
may never be granted from Rating alone.

## Release gates

The balance harness runs 1,000 players (200 per archetype) for ten seasons under focus,
balanced and recovery-aware policies. A separate lifespan-to-45 cohort is mandatory for
retirement because an age-18 ten-season cohort reaches only age 27/28.

MVP remains In Progress until a real two-season browser playthrough covers planning,
training/recovery, approaches, post-game, week simulation, season review,
awards/contract/offseason, next season, restart/reload, bench/DNP and injury states.
