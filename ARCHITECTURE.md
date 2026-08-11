# Architecture

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
                                                    React web client
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

`web/` is a React/Vite client. It consumes explicit `GameView` responses and does not sample outcomes or calculate game rules. Network/session state lives in `useGame`; focused components render score, matchup, diamond, controls, play log, and lineups. The browser is never authoritative.

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
quality. The season layer owns a deterministic six-team schedule and standings. Manager
persistence, result simulation, API, and UI remain later layers and must not weaken the
catalog or roster validation.
