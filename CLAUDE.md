# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Backend service for **Crew Shop**, a specialty coffee online marketplace. Python 3.13 / FastAPI, deployed and versioned independently of the web client. Broader architecture docs live in a separate `my_docs` repo, locally at `/Users/siarheisamoshyn/Projects/my_docs/docs/wiki/topics/crew/crew_shop/` (topic `crew/crew_shop`, start at `overview/repositories.md`).

## Working scope

The focus is implementing the **backend**. Allowed: read and modify this backend repository, and read and update the `my_docs` wiki (task docs, statuses, entity specs per their stability rules). All other repositories / projects are **read-only** — read them for context (house-style, contracts), but never modify them.

Do **not** use the persistent memory system. Record what was done in the relevant wiki task/docs, and capture any working rules here in this `CLAUDE.md`.

## Commands

Dependencies are managed with **uv** (`package = false` — this is an app, not a packaged library).

```bash
uv sync                       # install all deps including the dev group
uv run python runner.py       # run the API (dev: uvicorn w/ reload; prod/stage: execs gunicorn)
uv run pytest                 # run the test suite
uv run pytest tests/unit/test_health.py::test_liveness_returns_ok  # single test
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy src               # type-check (strict mode)

docker compose up --build     # run backend + PostgreSQL 17 locally (hot reload)
uv run alembic revision --autogenerate -m "msg"  # generate a migration (db must be up)
uv run alembic upgrade head   # apply migrations; `downgrade -1` to roll back
```

Full command reference (Docker lifecycle, migrations, host vs in-container) lives in `commands.md`.

`pytest` runs with `asyncio_mode = "auto"`, so `async def test_*` needs no decorator. `pythonpath = ["."]` makes the `src` package importable from the repo root.

## Environment & configuration

Configuration is **environment-driven** through `ENV` (`dev` | `stage` | `prod`), and several behaviors branch on it. Understanding this split is essential:

- **`src/bootstrap.py` must load before any `Settings` is instantiated.** It reads `ENV` and, for `dev` only, loads `.env.<env>` (e.g. `.env.dev`) via python-dotenv. In `stage`/`prod` no file is loaded — config comes from the real environment. `configs.py` imports `bootstrap` at module top precisely to guarantee this ordering; do not break that import.
- **Database URL is one complete DSN in every environment** (`Settings.get_database_url`): `DATABASE_URL`, from `.env.dev` locally and from the `crew-shop-db` Kubernetes Secret in the cluster. It fails loudly rather than booting unconfigured. `get_database_url_masked()` is the logging-safe variant (password redacted) — use it whenever a URL is logged.
- **`runner.py` also branches on env**: `prod`/`stage` `os.execvp` into gunicorn (uvicorn workers, `gunicorn.conf.py`); `dev` runs uvicorn in-process with reload.
- Copy `.env.example` to `.env.dev` for local work. `.env.*` is git-ignored except the example.

## Architecture

Single `src` package, layered under `src/api`. App wiring flows through `create_app()` in `src/api/app.py`: it builds the `FastAPI` instance, then in order registers **exception handlers → middleware → the v1 router**. A module-level `fastapi_app = create_app()` is what gunicorn/uvicorn import (`src:fastapi_app`).

- **Routing is versioned.** `src/api/v1/__init__.py` exposes `api_router` mounted at `/v1`; feature routers (health, auth, catalog, admin catalog, orders, admin orders, users, ratings, points, admin points, subscriptions, payments, payment methods) are included there. New endpoints belong under `src/api/v1/routers/` with Pydantic schemas in `src/api/v1/schemas/`.
- **Database access** (`src/api/core/database.py`): async SQLAlchemy 2.0 engine + `async_sessionmaker`. Inject sessions via the `get_db` FastAPI dependency, which **commits on success and rolls back on exception** automatically — endpoints should not commit manually. New ORM models extend `Base`; use `TimestampMixin` for `created_at`/`updated_at`. `close_db()` is called from the lifespan handler on shutdown.
- **Errors are returned in a single envelope.** Raise `AppException` (from `src/api/exceptions.py`) for app-level errors; handlers in `src/api/exception_handlers.py` convert every error class (`AppException`, `RequestValidationError`, Starlette `HTTPException`, and uncaught `Exception`) into `{"error": {error_code, status_code, message, request_id}}`. Add new error types as `AppException` subclasses rather than returning ad-hoc JSON.
- **Request logging middleware** (`src/api/middleware/logging.py`) assigns a `request_id` to `request.state` (consumed by the error envelope), logs each completed request, and sets `X-Request-ID` / `X-Process-Time` headers. CORS is configured first so preflight is handled before logging. Allowed origins come only from `CORS_ORIGINS` settings — never hardcode them.
- **Logging is structured JSON** for all environments (`src/api/core/logging_config.py`, via dictConfig). The `src` logger and uvicorn loggers route to stdout; SQLAlchemy is pinned to WARNING.

- **Migrations** (`alembic/`, async): `env.py` reads the URL from settings (not `alembic.ini`) and targets `Base.metadata`, which carries a `NAMING_CONVENTION` for deterministic autogenerate. New models must be imported in `env.py` to be seen. In the runtime Docker image use `alembic ...` directly (`uv` is build-stage only).

The domain layer is built out: eight domains (`auth`, `catalog`, `orders`, `payments`, `points`, `ratings`, `subscriptions`, `users`), fourteen routers under `/v1`, and a linear chain of migrations in `alembic/versions/`.

- **Authentication is delegated to crew_auth.** crew_shop issues no tokens. The SPA posts crew_auth's one-time code to `POST /v1/auth/session`; the code is redeemed server-side (`src/auth/crew_auth.py`) and the account is upserted on `users.auth_user_id`. Access tokens are crew_auth's RS256 JWTs, verified locally against its JWKS (`src/auth/jwks.py`) — no network call per request, and a crew_auth outage does not take authenticated traffic down. `users.id` is local and never leaves crew_shop; `auth_user_id` is the identifier for every external surface (admin API, logs, cross-service references).
- **Deployment is DigitalOcean, not Google Cloud.** Images go to GHCR and ArgoCD rolls them out on DOKS; migrations run as a `PreSync` hook Job. There is no Cloud Run, Cloud SQL, Artifact Registry or Firebase path left in this repo — do not reintroduce one.

---
title: Conventions
type: reference
tags: [conventions, rules, communication, code-style, standards]
sources: []
related: [_index.md, database/guidelines.md, backend/standards/exception-handling.md, backend/tech-stack.md, ui/web/tech-stack.md]
updated: 2026-05-24
stable: false
---

# Conventions

Working rules for Crew Shop: how we communicate and how we write code. Derived from the project rules. **Production-readiness and stability come first** — when writing code and executing tasks, the goal is a stable, production-grade solution, not a prototype.

## Communication

- **Language** — Russian for discussion of ideas and decisions; English for code, comments, and documentation.
- **Concise and direct** — state results and decisions; no narration of the thinking process.
- **No emoji** — in any communication.
- **Max 3 questions per message** — batch larger sets and wait for answers before the next batch.
- **Clarity first** — if something is unclear, ask before proceeding; do not assume. If a decision is deferred ("don't know" / "later"), record it in the todo with its context.
- **Disagree openly** — if a request seems wrong, say so with reasons and alternatives, then respect the final decision.

## Code

### Production focus and stability (primary)

- Write production-grade code, not prototypes. A task is done when it is correct, tested, and stable — not when it "runs once".
- Design for failure: validate at system boundaries (requests, external providers), use transactions for multi-step writes, and return the standard error envelope.
- No half-finished implementations, dead code, or leftover TODO stubs.
- Security by default: secrets only via environment (never committed), verify provider tokens server-side, parameterized queries, least-privilege database user.
- Observability: structured logging with request IDs (house-style); never log secrets or PII.
- Migrations are reversible and lossless; test `upgrade` and `downgrade` before merge.
- Performance: index foreign keys and filtered columns, pool connections, paginate large reads.

### Style and tooling

- **Language in code** — English only (identifiers, comments, docs).
- **Comments** — only when the *why* is non-obvious; one line; explain intent, not the obvious what.
- **Backend** — ruff (lint + format) + mypy (strict); follow the house-style structure (`src/api/{core,middleware,v1}`, domains as top-level `src/<domain>/`).
- **Web** — Biome (lint + format) + Steiger (FSD boundaries) + TypeScript strict; Feature-Sliced Design layers.
- Follow the documented standards: [Database Guidelines](database/guidelines.md), [Exception Handling](backend/standards/exception-handling.md), [Backend stack](backend/tech-stack.md), [Web stack](ui/web/tech-stack.md).

### Tests

- Cover the golden path and the key edge and failure cases. Backend: pytest (unit + integration against a real PostgreSQL). Web: Vitest + React Testing Library.
- A task's acceptance criteria must be verifiable and green before it is considered done.

### Commits

- Format: `[type]: [topic] - [description]` — types `docs | feat | fix | refactor | infrastructure`; topic is the folder or feature.
- One logical change per commit; separate commits per topic.
- Never commit secrets or generated artifacts.

## Tasks

- Implementation tasks (in [implementation/tasks/](implementation/tasks/_index.md)) state goal, scope, steps, acceptance criteria, and references — written so they can be implemented directly.
- Execute the agreed scope; if reality diverges from the task, flag it and update the doc rather than deviating silently.
- Prioritize correctness and stability over speed.
