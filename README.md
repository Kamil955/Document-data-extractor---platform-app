# Contract Extractor

Web app that ingests documents (contracts), answers questions about them with RAG,
and fills DOCX templates with extracted data. Templates can be created in the app.

Status: working end to end. Upload documents, extract template fields with a local model and
cited, verified quotes, review and correct the values next to the source, write the Word
template in the browser (with AI rewriting of selected text) and fill it. Open
http://localhost:3000 after `docker compose up --build`.

## Run everything with Docker

```bash
cp .env.example .env
docker compose up --build         # web app on :3000, API on :8000
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

# start extracting its fields from an indexed document: the answer is 202 at once, with the
# id of the extraction (the worker needs a few seconds per field)
curl -s -X POST localhost:8000/documents/$DOC/extract -H 'Content-Type: application/json' \
  -d "{\"template_id\": \"$TEMPLATE\"}" | python -m json.tool

# or without a stored template: send the fields inline
curl -s -X POST localhost:8000/documents/$DOC/extract -H 'Content-Type: application/json' \
  -d '{"fields": [{"key": "law", "label": "Governing law"}]}' | python -m json.tool

# poll the extraction: status is pending, running, completed or failed, and `results` grows
# by one field at a time (`total` is the number of fields)
curl -s localhost:8000/extractions/$EXTRACTION | python -m json.tool
```

The worker (the same process that indexes documents) runs the extractions one at a time, after
indexing. If Ollama is down the extraction stays `pending` and continues when it is back; fields
that are already done are kept, also when the worker itself dies. A person can correct values and
fill a Word file once the status is `completed` (or `failed`); before that the API answers 409.
`GET /documents/{id}/extractions` lists the extractions of a document.

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
# wait until `status` is "completed" (see above) before filling

curl -s -D - -o filled.docx -X POST localhost:8000/extractions/$EXTRACTION/fill \
  -F "file=@backend/examples/contract_summary_template.docx"
```

The `X-Fill-*` response headers list the placeholders that were filled, not found, unverified
(a value without a verified quote) or unknown (no such field). In the document, not found values
are marked yellow and unverified values turquoise. Placeholders are found even when Word splits
them over several runs; text boxes, footnotes and hyperlinks are not covered yet.

## Template documents

A template can keep its own Word document, so filling needs no upload each time:

```bash
# create a template straight from a Word file: every {{placeholder}} becomes a field
curl -s -X POST localhost:8000/templates/from-docx \
  -F "file=@backend/examples/agreement_summary_card.docx" | python -m json.tool

# or attach / replace the document of an existing template
curl -s -X PUT localhost:8000/templates/$TPL/docx -F "file=@my-template.docx"
# or generate a starter document from the fields (title + Field/Value table)
curl -s -X POST localhost:8000/templates/$TPL/docx/generate

curl -s localhost:8000/templates/$TPL/preview | python -m json.tool   # structured preview
curl -s -o template.docx localhost:8000/templates/$TPL/docx           # download

# fill from the template's own document: no file in the request
curl -s -D - -o filled.docx -X POST localhost:8000/extractions/$EXTRACTION/fill
```

The preview is structured JSON (paragraphs, tables, `{{placeholders}}` marked as known or
unknown, template fields the document never uses), never HTML, so the frontend renders it as
plain text. Headers, footers, images and text boxes are not shown in the preview.
`backend/examples/agreement_summary_card.docx` matches `template_contract_basics.json`; rebuild
it with `uv run python examples/build_example_templates.py`. In the frontend, the **Templates**
page creates a template from a Word file and its page shows the document with the placeholders
highlighted (green = a field fills it, red = no such field).

## Template editor and AI rewrite

A template's document can be written and edited in the browser (`/templates/{id}/edit`): a paper
page with headings, bold/italic/underline, bullet lists and tables, and a Fields panel whose
entries insert `{{placeholders}}` at the cursor (typing `{{key}}` works too). Placeholders that
are not fields of the template are drawn red. Select text inside one paragraph and press
**Ask AI** (or Ctrl+K) to rewrite it: pick a preset ("Make it more formal") or type your own
instruction, read the suggestion and press **Replace selection**; nothing changes before that.

```bash
curl -s localhost:8000/templates/$TPL/content | python -m json.tool          # blocks for the editor
curl -s -X PUT localhost:8000/templates/$TPL/content -H 'Content-Type: application/json' \
  -d '{"blocks": [...]}'                                                       # save as the DOCX
curl -s -X POST localhost:8000/templates/rewrite -H 'Content-Type: application/json' \
  -d '{"text": "We agree.", "instruction": "Make it more formal"}'
```

Saving rebuilds the **body** of the Word file from the editor's blocks. The styles, headers,
footers and page setup of the existing file are kept; direct formatting (fonts, colours,
alignment), images, merged cells and hyperlinks are not, and the editor lists what the current
file would lose before you save. A document over 1500 blocks is refused instead of being cut.
The rewrite uses the same local model as the extraction; the answer must contain exactly the
`{{placeholders}}` of the original passage (one retry, then an error), so a rewrite cannot
silently break the template.

## Frontend (review screen)

A Next.js app (TypeScript, Tailwind) on top of the API: upload documents, define templates, run
an extraction and review every value next to its quote and page. A value without a verified quote
is marked "Needs check"; you can correct or confirm it (`PATCH /extractions/{id}/values/{key}`),
then fill a Word template from the confirmed values. "Show in document" under a quote opens
the source in a side panel: the PDF page with the quote highlighted (pdf.js, in the browser), or
the cited passage as text for Word files. The highlight is found by comparing letters and digits
only, so differences in line breaks, hyphenation and spacing between the PDF and the text the
model saw do not matter; if the quote cannot be found on the page, the panel says so.

The web app is part of `docker compose up` (service `frontend`, a production build served on
port 3000). For development with hot reload, stop that service and run it from source:

```bash
docker compose up -d --build   # the API must be running
docker compose stop frontend
cd frontend
npm ci
npm run dev                    # http://localhost:3000
```

The image is built in three stages (install, build, run) from Next.js's `standalone` output,
so it holds only the server and what it needs. `NEXT_PUBLIC_API_URL` is compiled into the
page at build time: set it (in `.env` or the environment) before `docker compose build` when the
API is not at http://localhost:8000 for the browser.

The API address is `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). The API allows
the origin `http://localhost:3000` (CORS); to serve the frontend from another origin set
`CORS_ORIGINS='["https://your.host"]'` for the backend. Checks: `npm run lint`,
`npm test`, `npx tsc --noEmit`, `npm run build` (CI runs all of them).
