# Architecture

## Phase 1 production topology

```text
GitHub Pages (static React + TypeScript + Vite)
        |
        | HTTPS JSON API
        v
ngrok HTTPS endpoint
        |
        v
Linux host loopback 127.0.0.1:8000
        |
        v
FastAPI authoritative backend
        |-- ratings and matchup simulation
        |-- game state machine
        |-- Career and Manager services
        `-- SQLite persistence / read-only rating artifacts

SQL Server 127.0.0.1:1433 (research/export source only)
```

The two deployables are intentionally separate. GitHub Pages owns rendering, UI state,
and API calls only. It contains no probability model, rating computation, progression,
ownership, SQL connection, or authoritative match state. FastAPI never depends on the
frontend build and does not serve `web/dist` in production.

The browser obtains the API origin only from `VITE_API_BASE_URL`. The production value is
a GitHub repository variable injected by the Pages workflow; no ngrok URL is committed.
All browser requests pass through the shared `web/src/api/client.ts` layer, which applies
a ten-second timeout and converts transport failures into player-facing messages.

FastAPI is reachable on the Linux host only through `127.0.0.1:8000`. ngrok is the sole
Phase 1 public ingress. CORS permits the actual Pages origin and explicit localhost
development origins, never `*`. SQL Server remains loopback-only and is never contacted
by the browser. Replacing ngrok with a fixed HTTPS API origin later changes deployment
configuration, not the game domain.

## System boundaries

```text
BaseballRealData (immutable SQL Server)
        |
        v
ratings adapter -> versioned game rating artifacts -> pure simulation domain
                                                    |-> CLI / Monte Carlo
                                                    |-> FastAPI adapter
                                                    |-> game state machine
                                                    |-> career / manager services
                                                             |
                                                             v
                                                  separate game persistence
                                                             |
                                                    v
                                            HTTPS API response
```

## Repository boundary

`cpbl-baseball-sim` is independent from `/home/chester/baseball-data`. The data project remains the crawler and research source; this project owns game-domain code and derived artifacts. GitHub publication occurs after the Phase 1 MVP gate.

## Planned packages

- `baseball_sim.ratings`: immutable rating contracts, source adapters, versioned snapshots.
- `baseball_sim.simulation`: pure plate-appearance probability and Monte Carlo logic.
- `baseball_sim.game`: innings, outs, bases, lineup, scoring, and deterministic state transitions.
- `baseball_sim.career`: created-player progression and career saves.
- `baseball_sim.manager`: roster constraints, lineups, bullpen, standings.
- `baseball_sim.api`: FastAPI adapters; no domain probability logic.
- `web`: React + TypeScript + Vite client; no authoritative outcomes.

## Core rules

- Domain packages do not import FastAPI or React.
- Runtime outcomes come from seeded probabilistic functions, not an LLM.
- All probability vectors are validated, bounded, and normalized.
- Game persistence uses a separate database/schema and stores model/data versions.
- Server is authoritative for outcomes, progression, ownership, and saves.

## Initial PA model research shape

Start from completed-season CPBL league outcome probabilities. Decompose a PA hierarchically into free pass, strikeout, ball in play, then hit type. Compare log-odds, multiplicative odds, and bounded hierarchical adjustments. The accepted model must preserve probability mass and pass sensitivity, interaction, and Monte Carlo regression gates.
## M4 HTTP and client boundary

`baseball_sim.api` is a thin FastAPI adapter over the pure game domain. It owns HTTP validation and an in-memory session repository, but never recalculates probabilities, advances runners, or queries raw SQL. Batch mutations commit only after reaching their target state.

`web/` is a separately deployed React/Vite client. It consumes explicit `GameView`
responses and does not sample outcomes or calculate game rules. Network/session state
lives in `useGame`; focused components render score, matchup, diamond, controls, play
log, and lineups. localStorage may retain the last game ID and UI preferences, but never
the authoritative game payload. The browser is never authoritative.

## M5 Career boundary

`baseball_sim.career` is an immutable, batter-only event-sourced domain. Created players
own four Composite Scores; the existing mapping derives Raw and Display ratings. Career
simulation reuses the M3 nine-inning `GameState` and counter sampler. A neutral fixture
supplies the other eight lineup slots and both pitchers while the created batter occupies
the away leadoff slot. The complete inning, outs, bases, score, lineups, and pitchers are
persisted after every internal PA; only a finished game increments completed games and
materializes the created batter's counting stats.
Season and career rates are derived from counting totals, never averaged.

The HTTP adapter persists validated domain JSON inside a separate local SQLite database.
Each mutation atomically checks an expected revision, applies one domain operation,
autosaves, and records compact operation metadata for retry safety without duplicating
the growing event payload. Clients supply UUID identifiers,
not paths. `BaseballRealData` remains outside this boundary and untouched.

## M6 Manager boundary

`baseball_sim.manager` loads `rating-snapshot-v0.2` through its hash-pinned manifest;
runtime Manager games never query SQL. The catalog preserves Score and RatingRaw, derives
neutral-65 analytic PA impact, and assigns versioned completed-pool tiers and costs.
Incomplete 2026 cards remain visible but have no competitive tier or cost.

Roster legality is a pure aggregate over canonical player-season cards. Static
`ProfilePosition` remains exact for display; LF/CF/RF additionally qualify for the OF
family, while Fielding and multi-position skill are explicitly outside this contract.
The per-game roster layer adds an exact-position lineup, bench, rotation, bullpen,
PA-boundary substitutions, and Stamina-derived pitcher BF capacity without changing PA
quality. The season layer owns a deterministic six-team schedule and standings. The
application layer persists canonical card IDs, frozen schedule identity, pitcher
availability, results, catalog fingerprint, revision, and compact idempotency metadata
in a separate SQLite database. FastAPI and React are adapters over that state; neither
can bypass catalog or roster validation. Preseason replacement rebuilds and validates
the full six-team league atomically, and the first game locks every roster.

Manager game orchestration connects those layers without introducing a second outcome
engine. `ManagerGameSession` advances the authoritative M3 state one PA at a time using
the selected cards' full-precision Raw ratings. `PitcherAvailability` supplies a rested
four-man rotation and excludes relievers after two consecutive team games. A complete
six-team league owns its frozen schedule, usage state, results, and derived standings;
fixed seeds reproduce the same games and season at domain level.

The Manager UI consumes full-precision Raw ratings for gameplay and displays tiers and
costs without inventing an Overall rating. Its roster builder fetches compatible real-card
candidates, but legality remains server-authoritative: budget 70, SSR/SR caps, distinct
positions, pitching roles, PlayerID uniqueness, and cross-team CardID ownership are
checked together before a new revision is saved.
