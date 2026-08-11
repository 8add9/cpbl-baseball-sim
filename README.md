# CPBL Baseball Sim

Independent, server-authoritative numerical baseball game built from versioned CPBL-derived player-season ratings.

The project is in Phase 1. Foundation, Rating Engine, matchup model, game state,
Text Game, and Career Mode 1-1 are complete. Manager Mode is the next milestone.

## Development

```bash
uv sync --frozen --all-groups
uv run pytest
uv run ruff check .
uv run mypy
```

Generate a deterministic rating snapshot on the server:

```bash
baseball-rating-export \
  --data-dir /home/chester/baseball-data \
  --output-dir artifacts/generated/ratings \
  --env .env
```

Historical raw data remains in the separate `/home/chester/baseball-data` project and `BaseballRealData` SQL Server database. This project uses a SELECT-only identity and never writes game data into the historical source.

Run a deterministic 100,000-PA matchup:

```bash
baseball-sim matchup \
  --contact 65 --power 100 --eye 65 \
  --stuff 65 --control 65 --hr-suppression 65 \
  --pa 100000 --seed 20260811 --model hierarchical
```

The CLI prints both analytic probabilities and sampled counts/slash line. Rating inputs are full-precision raw values in the open interval `(30, 110)`; integer display ratings are never simulation inputs.

## Text Game development

Start the API:

```bash
uv run uvicorn baseball_sim.api.app:app --host 127.0.0.1 --port 8000
```

In a second terminal, start React:

```bash
cd web
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`. Text Game supports next PA, half/full-game simulation,
and deterministic reset. Choose **生涯模式** to create an age-18 batter, simulate a
season, earn participation XP/development points, train Contact/Power/Eye, inspect the
read-only SpeedProxy, and
resume an autosaved local career after an API restart. Set `BASEBALL_SIM_DATA_DIR` to
choose the local SQLite save directory.
