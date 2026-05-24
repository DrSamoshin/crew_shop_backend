# crew_shop_backend

Backend service for Crew Shop — a premium specialty coffee online marketplace.

Python 3.13 / FastAPI service. Deployed and versioned independently of the web client.

## Local development with Docker

Runs the backend and PostgreSQL 17 with a single command, with hot reload and persistent database data.

```bash
cp .env.example .env.dev        # first time only; .env.* is git-ignored
docker compose up --build       # starts db (Postgres 17) + backend
```

- API: http://localhost:8080 — `GET /v1/health/live` → `{"status":"ok"}`; docs at `/docs`.
- The backend waits for the database to be healthy before starting.
- Editing files under `src/` hot-reloads the backend.
- Inside compose `DATABASE_URL` points at the `db` service (overridden in `docker-compose.yml`); the host is the compose service name, not `localhost`.

```bash
docker compose down             # stop (database data persists in the pgdata volume)
docker compose down -v          # stop and wipe the database
```

The production image uses the same `docker/Dockerfile`; for prod build with `uv sync --frozen --no-dev` and without the source mount.

## Database migrations (Alembic)

Alembic is configured with an async engine. The database URL comes from app settings (`env.py`), never from `alembic.ini`. Migration files are timestamped (UTC), e.g. `2026_05_24_1007-<rev>_<slug>.py`, and live in `alembic/versions/`.

On the host (database reachable on `localhost:5432`, e.g. `docker compose up -d db`):

```bash
uv run alembic revision --autogenerate -m "describe change"   # generate
uv run alembic upgrade head                                    # apply
uv run alembic downgrade -1                                    # roll back one
```

Inside Docker (the runtime image has `alembic` on PATH via `.venv`; `uv` is build-only):

```bash
docker compose run --rm backend alembic upgrade head
```

New models must be imported in `alembic/env.py` (so their tables register on `Base.metadata`) before autogenerate will see them. Always review and test `upgrade` and `downgrade` before merge.

## Documentation

Project wiki: `my_docs` repository, topic `crew/crew_shop` (start at `overview/repositories.md`).
