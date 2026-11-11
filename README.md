# Contract Extractor

Web app that ingests documents (contracts), answers questions about them with RAG,
and fills DOCX templates with extracted data. Templates can be created in the app.

Status: **stage 0** (skeleton). Roadmap: ingestion -> RAG with citations ->
templates and field schema -> filling -> template builder -> online editor.

## Run everything with Docker

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/health        # {"status":"ok"}
curl localhost:8000/health/ready  # {"status":"ready"}
```

## Backend development (without Docker for the API)

Start only the database, then run the API on the host:

```bash
docker compose up -d postgres
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://contract:contract@localhost:5432/contract
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Checks (the same ones CI runs)

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run alembic upgrade head && uv run alembic check
uv run pytest                      # all tests (needs Postgres)
uv run pytest -m "not integration" # tests without a database
```

## Migrations

After changing a model:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Always read the generated file before committing it. `alembic check` in CI fails
when models and migrations drift apart.
