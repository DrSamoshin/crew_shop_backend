# Migration Scripts

Scripts for applying database migrations to Cloud SQL environments via the Cloud SQL Auth Proxy.

## Prerequisites

1. Install cloud_sql_proxy:
   ```bash
   brew install cloud-sql-proxy
   ```

2. Authenticate Application Default Credentials (the proxy uses ADC, not `gcloud auth login`):
   ```bash
   gcloud auth application-default login
   ```

3. Configure the per-environment file in `alembic/scripts/` with real credentials.
   These files are git-ignored.

## Environment File Format

`alembic/scripts/.env.prod`:

```bash
DATABASE_HOST=project:region:instance
DATABASE_USER=username
DATABASE_PASSWORD=password
DATABASE_NAME=database_name
PROXY_PORT=5435
```

## Usage

### Apply migrations

```bash
./alembic/scripts/migrate.sh prod            # defaults to: upgrade head
./alembic/scripts/migrate.sh prod upgrade head
```

### Check current version

```bash
./alembic/scripts/migrate.sh prod current
```

### Downgrade / history

```bash
./alembic/scripts/migrate.sh prod downgrade -1
./alembic/scripts/migrate.sh prod history
```

### Reset database (stage only)

Drops all tables via `DROP SCHEMA public CASCADE` and reapplies all migrations.
Guarded to the `stage` environment only and requires typing `stage` to confirm.
Not available for prod.

```bash
./alembic/scripts/migrate.sh stage reset
```

## Security

Per-environment files (`.env.prod`, `.env.stage`) contain credentials and are git-ignored.
