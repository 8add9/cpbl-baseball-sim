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
