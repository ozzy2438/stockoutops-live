# AGENTS.md

## Cursor Cloud specific instructions

This is **StockoutOps Live** — a Python 3.12 / FastAPI human-supervised stockout
decisioning slice backed by PostgreSQL 16. Reasoning uses a deterministic stub
(no OpenAI/network call) and the app performs **no external writes**. See
`README.md` ("M1 local execution") and the `Makefile` for the canonical commands;
this section only records the non-obvious, Cursor-Cloud-specific caveats.

### What the update script already did

The startup update script runs `make setup`, which (re)creates the `.venv`,
`pip install -e ".[test]"`, and regenerates the git-ignored `.local/identities.json`
bearer tokens. You do **not** need to re-run it. All Python commands live in
`.venv/bin/` (e.g. `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/ruff`).

### Start PostgreSQL before doing anything (NOT handled by the update script)

PostgreSQL 16 is pre-installed in the base image, but it is a service and is **not**
started by the update script. Start it at the beginning of every session:

```bash
sudo pg_ctlcluster 16 main start   # idempotent-ish; safe to run, ignore "already running"
```

The migration role/database are created once and persist in the cluster data dir.
If a fresh machine is missing them (connection auth fails), recreate them:

```bash
sudo -u postgres psql -c "CREATE ROLE stockoutops_migration LOGIN PASSWORD 'migration-local-only' CREATEROLE;"
sudo -u postgres createdb -O stockoutops_migration stockoutops
```

The restricted runtime role `stockoutops_app` (password `app-local-only`) is created
automatically by the migration step — do not create it by hand.

### Required environment variables

The app/CLIs read config from the environment (there is no dotenv autoloader), so
export these before running anything. Values are the local-only ones from
`.env.example`:

```bash
export APP_ENV=local IDENTITY_PROVIDER=simulated REASONING_PROVIDER=stub
export SIMULATED_IDENTITIES_FILE=.local/identities.json
export DATABASE_URL="postgresql://stockoutops_app:app-local-only@localhost:5432/stockoutops"
export MIGRATION_DATABASE_URL="postgresql://stockoutops_migration:migration-local-only@localhost:5432/stockoutops"
export TEST_DATABASE_URL="postgresql://stockoutops_app:app-local-only@localhost:5432/stockoutops"
export APP_DB_PASSWORD=app-local-only
```

### Bring-up, run, and verify

After PostgreSQL is up and the env vars are exported:

```bash
make migrate     # apply ordered SQL migrations (idempotent; forward-only)
make seed        # verify + seed the SHA-256 fixture manifest (required; app has no evidence without it)
make serve       # uvicorn on http://127.0.0.1:8000  (review UI at /review)
make smoke-stub  # deterministic end-to-end smoke against a running server
make lint        # ruff format --check + ruff check
make test        # full pytest suite (unit + PostgreSQL integration); ~50s, needs DB running
```

Run a long-lived `make serve` in a tmux session (not a one-shot background process).

### Non-obvious gotchas

- `make test` and the `integration`-marked tests require PostgreSQL to be running;
  they connect to the real cluster, not a mock. If they hang/fail on connection,
  the cluster is not started.
- The happy-path fixture is `SKU-001 / STORE-001 / SUPPLIER-001`, which yields a
  cited draft in state `awaiting_human` that a reviewer can approve. Other SKUs
  (e.g. `SKU-002`) intentionally **fail-closed to `escalated`** with no draft, so
  a `POST .../review {"action":"approve"}` on them returns HTTP 422 — that is
  expected behavior, not a bug.
- The review flow is: operator `POST /v1/investigations` (needs an `Idempotency-Key`
  header + bearer token from `.local/*.token`) → reviewer `POST /v1/investigations/{id}/review`
  with the returned `draft_hash`. Identity/tenant/role are server-derived; passing
  `actor_id`/`tenant_id`/`role`/`roles` as query params is rejected with HTTP 400.
- Docker Compose (`make up`) is the README's recommended path but Docker is not
  installed in Cursor Cloud; use the host-Python path above (same as CI in
  `.github/workflows/ci.yml`).
- `make setup` regenerates `.local` bearer tokens each run, so tokens captured
  before a re-run become stale; restart `make serve` after re-running setup.
