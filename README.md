# CPBL Baseball Sim

Independent, server-authoritative numerical baseball game built from versioned CPBL-derived player-season ratings.

The project is in Phase 1. The engineering foundation and Rating Engine v0.1 are complete; the batter-versus-pitcher CLI checkpoint is in progress. Career and Manager modes intentionally have not started.

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
