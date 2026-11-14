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


## Templates and extraction

A template is a list of fields to extract (key, label, optional description, type: `text`,
`number`, `date`, `boolean`). It says what to look for, not where, so one template can be used
on any document.

```bash
# create a template (an example is in backend/examples)
curl -s -X POST localhost:8000/templates -H 'Content-Type: application/json' \
  -d @backend/examples/template_contract_basics.json | python -m json.tool

# extract its fields from an indexed document (a few seconds per field)
curl -s -X POST localhost:8000/documents/$DOC/extract -H 'Content-Type: application/json' \
  -d "{\"template_id\": \"$TEMPLATE\"}" | python -m json.tool

# or without a stored template: send the fields inline
curl -s -X POST localhost:8000/documents/$DOC/extract -H 'Content-Type: application/json' \
  -d '{"fields": [{"key": "law", "label": "Governing law"}]}' | python -m json.tool
```

Every value has `citations` with a quote that was checked against the document text.
`supported: false` with `found: true` means the model could not back the value with a real
quote: have a person check it. `DELETE /templates/{id}` and `DELETE /documents/{id}` remove
a template or a document (with its chunks and file).

### Search modes

`/search` takes `mode`: `vector` (default, by meaning) or `hybrid` (meaning plus Postgres
full-text keywords, merged with Reciprocal Rank Fusion). On three real contracts hybrid was
worse (hit@1 100% -> 79% and 80% -> 60%), so it is not the default. Compare with:

```bash
for m in vector hybrid; do
  uv run python -m app.evaluation.run --document $DOC --mode $m eval/uw_mutual_nda.json | tail -1
done
```

## Filling a Word template

An extraction is saved (`extraction_id` in the response of `/documents/{id}/extract`), so it can
be used without asking the model again. A Word file with placeholders `{{field_key}}` is filled
from it:

```bash
EXTRACTION=$(curl -s -X POST localhost:8000/documents/$DOC/extract -H 'Content-Type: application/json' \
  -d "{\"template_id\": \"$TPL\"}" | python -c 'import json,sys; print(json.load(sys.stdin)["extraction_id"])')

curl -s -D - -o filled.docx -X POST localhost:8000/extractions/$EXTRACTION/fill \
  -F "file=@backend/examples/contract_summary_template.docx"
```

The `X-Fill-*` response headers list the placeholders that were filled, not found, unverified
(a value without a verified quote) or unknown (no such field). In the document, not found values
are marked yellow and unverified values turquoise. Placeholders are found even when Word splits
them over several runs; text boxes, footnotes and hyperlinks are not covered yet.

## Frontend (review screen)

A Next.js app (TypeScript, Tailwind) on top of the API: upload documents, define templates, run
an extraction and review every value next to its quote and page. A value without a verified quote
is marked "Needs check"; you can correct or confirm it (`PATCH /extractions/{id}/values/{key}`),
then fill a Word template from the confirmed values.

```bash
docker compose up -d --build   # the API must be running
cd frontend
npm ci
npm run dev                    # http://localhost:3000
```

The API address is `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). The API allows
the origin `http://localhost:3000` (CORS); to serve the frontend from another origin set
`CORS_ORIGINS='["https://your.host"]'` for the backend. Checks: `npm run lint`,
`npx tsc --noEmit`, `npm run build` (CI runs all three).
