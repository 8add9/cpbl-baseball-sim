# CPBL Baseball Sim

Independent, server-authoritative numerical baseball game built from versioned CPBL-derived player-season ratings.

The project is in Phase 1. The engineering foundation, Rating Engine v0.1, and first batter-versus-pitcher Monte Carlo checkpoint are complete. Career and Manager modes intentionally have not started.

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
