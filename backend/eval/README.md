# Retrieval evaluation

Each question file is a JSON list of `{"question", "expected_sections", "expected_text"}`.
A search hit counts as correct when its `section_path` is an expected section (or one of
its sub-sections) OR its text contains one of the expected snippets (case and line breaks
are ignored). At least one of the two lists must be given. Sections suit documents with
numbered headings, snippets suit documents without them.

| File | Document | Structure |
|------|----------|-----------|
| `richtech_msa.json` | Master IT Services and Products Agreement, SEC EDGAR Exhibit 10.3 (Richtech Robotics, 2023). Print the EDGAR page to PDF. | long (83 pages), nested numbering, tables, many redactions |
| `uw_mutual_nda.json` | University of Washington sample mutual NDA: https://research.washington.edu/research/wp-content/uploads/mnda-sample-template.2025.pdf | short, 8 titled sections |
| `cornell_contractor.json` | Cornell ILR independent contractor contract template: https://www.ilr.cornell.edu/sites/default/files-d8/Independent-Contractor-Form-Approved-Template-Final-as-of-September-1-2013-3.pdf | numbered clauses WITHOUT headings |

Run (API running, document uploaded and `indexed`):

    cd backend
    uv run python -m app.evaluation.run --document <id> eval/uw_mutual_nda.json

Questions whose expected section/snippet has no chunk in the index are reported as `SKIP`
and left out of the metrics: they cannot be answered, which is a flaw of the question, not
of the search (for example, sections that are fully redacted in the public EDGAR filing).

The expected sections and snippets come from outlines of the documents and were NOT all
verified against the full text. Treat a miss as a prompt to read the section: the question
or the expectation may be wrong, not only the search.

## Answer evaluation (`/ask`)

`answers_*.json` hold questions with the expected answer (`expected_any`: the answer must
contain at least one of the snippets) or `"expect_found": false` for questions the document
cannot answer (the model must say so instead of inventing something).

    uv run python -m app.evaluation.run_ask --document <id> eval/answers_uw_mutual_nda.json

The report counts correct answers, answers without a verified quote, answers to unanswerable
questions and the time per question. To compare models, restart the API with another
`LLM_MODEL` (for example `qwen3.5:9b` and `gemma4:12b`) and run the same files. The snippets
come from outlines of the documents and may need small corrections after the first run.
