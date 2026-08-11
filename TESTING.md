# Testing Strategy

## Test layers

- Unit: rating mapping, odds transforms, probability decomposition, base advancement, scoring, progression costs.
- Property: finite/bounded/sum-to-one probabilities, monotonic rating effects, legal state transitions, save round-trips.
- Golden matchup: versioned fixed archetypes and selected historical cards with fixed seeds.
- Monte Carlo: at least 100,000 PA per core comparison; larger samples for rare outcomes.
- Integration: read-only rating source, API/domain contracts, persistence, deterministic replay.
- Browser: real Text Game, Career, and Manager workflows.

## Initial golden grid

Vary one rating at a time through 50, 65, 80, 95, 105 for Contact, Power, Eye, Stuff, Control, and HRSuppression. Hold all other values at65. Assert expected monotonic outcomes and minimum meaningful effect sizes after empirical calibration.

## Required interaction fixtures

- High Power + low Contact
- High Contact + low Power
- High Eye + low Contact
- High Stuff + poor Control
- Low Stuff + elite Control
- Elite Stuff + elite Contact
- Elite Power + elite HRSuppression

## Reproducibility

Every simulation entry point accepts a seed. Tests compare deterministic counts for a fixed engine version and statistical bands for cross-version balance behavior.

M2 evidence is generated reproducibly with:

```bash
uv run python research/matchup_model_research.py
```

It writes the three-model comparison, calibrated coefficient evidence, and fixed-seed Power 65 vs 100 checkpoint under `artifacts/research/`, plus `research/pa_matchup_model_report.md`.

Run the M3 complete-game validation with:

```bash
uv run python research/game_state_validation.py
```

The 1,000-game fixture checks legal termination and aggregate diagnostics. Its run environment is not a historical calibration target because runner advancement is deliberately simplified.

M4 web checks:

```bash
uv run pytest tests/api
cd web
npm ci
npm run lint
npm run test
npm run build
npm audit --audit-level=low
```

Browser QA uses the in-app Browser at 1440×1000 and 390×844. The required interaction path is initial create → next PA → simulate half → simulate full → reset, with DOM state checks and console inspection after each mutation.

M5 Career checks add:

```bash
uv run pytest tests/career tests/api/test_career_api.py
cd web
npm run lint
npm test -- --run
npm run build
```

The browser regression creates a Power archetype with explicit position/bats/throws,
plays one PA, restarts the API with that partial game, quick-finishes it, simulates three
six-game weeks, trains Power, and advances to the next event. Desktop and mobile checks
assert actual CSS grid columns, document width, four controls, read-only SpeedProxy, and
clean console output. The QA-only save is removed after the run.

Run the live read-only Rating Engine contract on the server with:

```bash
BASEBALL_DATA_INTEGRATION=1 \
BASEBALL_DATA_DIR=/home/chester/baseball-data \
BASEBALL_DATA_ENV=.env \
uv run pytest tests/integration/test_live_rating_export.py
```

## Milestone rule

A green build is insufficient. Each milestone requires its acceptance tests, actual execution, QA evidence, bug fixes, and current documentation.
