# Contract Extractor

Web app that ingests documents (contracts), answers questions about them with RAG,
and fills DOCX templates with extracted data. Templates can be created in the app.

Status: **stage 2, part 1** (upload, indexing, semantic search, retrieval evaluation). Roadmap: RAG with citations -> templates and field schema -> filling -> template builder -> online editor.

## Run everything with Docker

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/health        # {"status":"ok"}
curl localhost:8000/health/ready  # {"status":"ready"}

# upload a PDF or DOCX, then read it back
curl -F "file=@contract.pdf" localhost:8000/documents
curl localhost:8000/documents
curl -OJ localhost:8000/documents/<id>/file
```

Uploaded documents are indexed in the background by the worker (status `uploaded` ->
`processing` -> `indexed` or `failed`):

```bash
curl localhost:8000/documents/<id>/chunks      # text, pages, section of each chunk
curl -X POST localhost:8000/documents/<id>/reprocess   # retry a failed document
```

### Embeddings need Ollama on the host

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-embedding:0.6b
```

While Ollama is unreachable the worker keeps documents in `uploaded` and retries;
they are not marked `failed`.

### Search and evaluation

```bash
curl -s -X POST localhost:8000/search -H 'Content-Type: application/json' \
  -d '{"query": "how are invoices paid?", "limit": 5}'
```

Answers with citations (needs a language model in Ollama):

```bash
ollama pull qwen3.5:9b
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "How much notice is needed to terminate?"}'
```

The response contains `found`, `answer`, `supported` (true only when a citation was verified
against the source text) and the citations with page and section. Retrieval and answer
quality are measured against question sets, see `backend/eval/README.md`.

Interactive API docs: http://localhost:8000/docs

## Backend development (without Docker for the API)

Start the database and the storage emulator, then run the API on the host:

```bash
docker compose up -d postgres floci-az
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://contract:contract@localhost:5432/contract
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# in a second terminal: the ingestion worker
uv run python -m app.ingestion.worker
```

## Checks (the same ones CI runs)

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run alembic upgrade head && uv run alembic check
uv run pytest                      # all tests (needs Postgres and floci-az)
uv run pytest -m "not integration" # tests without a database
```

## Migrations

After changing a model:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Always read the generated file before committing it. `alembic check` in CI fails
when models and migrations drift apart.
