# Commands

## Run with Docker (local: backend + PostgreSQL 17)

```bash
cp .env.example .env.dev        # first time only (.env.* is git-ignored; .env.dev already present)
docker compose up --build       # build and start db + backend (foreground)
docker compose up --build -d    # same, detached (background)
```

- API: http://localhost:8080 — `GET /v1/health/live` → `{"status":"ok"}`; docs at `/docs`.
- Backend starts only after the database is healthy; edits under `src/` hot-reload.

```bash
docker compose logs -f backend  # follow backend logs
docker compose ps               # container status
docker compose down             # stop (database data persists in the pgdata volume)
docker compose down -v          # stop and wipe the database
```

## Run without Docker

```bash
uv sync                         # install all deps (incl. dev group)
uv run python runner.py         # run the API (dev: uvicorn w/ reload)
```

## Stop the backend

```bash
# Docker
docker compose down             # stop backend + db (data persists in pgdata)
docker compose stop backend     # stop only the backend, keep db running

# Foreground `uv run python runner.py`: press Ctrl+C in that terminal

# Background / unknown: kill whatever listens on port 8080
lsof -ti :8080 | xargs kill      # SIGTERM
lsof -ti :8080 | xargs kill -9   # force, if it ignores SIGTERM
pkill -f runner.py               # or by process name
```

## Migrations (Alembic)

```bash
docker compose up -d db                                       # Postgres on localhost:5432
uv run alembic revision --autogenerate -m "describe change"   # generate
uv run alembic upgrade head                                   # apply
uv run alembic downgrade -1                                   # roll back one
uv run alembic current                                        # show current revision

docker compose run --rm backend alembic upgrade head          # apply inside Docker
```

## Tests, lint, types

```bash
uv run pytest                   # run the test suite
uv run pytest tests/unit/test_health.py::test_liveness_returns_ok  # single test
uv run ruff check .             # lint
uv run ruff format .            # format
uv run mypy src                 # type-check (strict)
```
