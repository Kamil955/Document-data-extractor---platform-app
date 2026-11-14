"""Measure field extraction against known values.

Usage (API and Ollama running, document indexed):
    uv run python -m app.evaluation.run_extract --document <id> eval/fields_uw_mutual_nda.json

The file is a list of fields. Each field is what /extract takes (key, label, description, type)
plus its expectation: "expected_any" (snippets, one of which the value must contain) or
"expect_found": false (the document does not state it, so the right result is "not found").

Compare settings on the same fields, for example --limit 5 | 8 | 10.
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from app.evaluation.metrics import grade_answer

_REQUEST_KEYS = ("key", "label", "description", "type")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fields", type=Path)
    parser.add_argument("--document", type=uuid.UUID, required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    items = json.loads(args.fields.read_text(encoding="utf-8"))
    request_fields = [{k: item[k] for k in _REQUEST_KEYS if k in item} for item in items]
    started = time.monotonic()
    with httpx.Client(base_url=args.api, timeout=1200) as client:
        response = client.post(
            f"/documents/{args.document}/extract",
            json={"fields": request_fields, "limit": args.limit},
        )
        response.raise_for_status()
    took = time.monotonic() - started
    body = response.json()

    correct = unsupported = wrongly_found = 0
    for item, result in zip(items, body["results"], strict=True):
        grade = grade_answer(item, {**result, "answer": result["value"]})
        correct += grade.correct
        unsupported += grade.found and not grade.supported
        wrongly_found += (not item.get("expect_found", True)) and grade.found
        flag = "  [UNSUPPORTED]" if grade.found and not grade.supported else ""
        print(f"{'OK  ' if grade.correct else 'FAIL'} {item['key']}{flag}")
        if not grade.correct or flag:
            print(f"       value: {result['value'][:100]!r} (found={result['found']})")
            cited = [c["section_path"] for c in result["citations"]]
            retrieved = [r["section_path"] for r in result["retrieved"]]
            print(f"       cited: {cited}  retrieved: {retrieved}")

    n = len(items)
    print(
        f"\n[limit {args.limit}] model {body['model']} | {correct}/{n} correct "
        f"({correct / n:.0%}) | {unsupported} values without a verified quote | "
        f"{wrongly_found} values for fields the document does not state | {took:.0f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
