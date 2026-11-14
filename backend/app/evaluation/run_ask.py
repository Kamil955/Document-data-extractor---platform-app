"""Measure the quality of /ask answers against hand-written questions with known answers.

Usage (API and Ollama running, document indexed):
    uv run python -m app.evaluation.run_ask --document <id> eval/answers_uw_mutual_nda.json

A question with only "expected_sections" (the retrieval sets work as they are) is graded by the
clause its verified citation comes from; one with "expected_any" by the answer text.

Compare models by restarting the API with another model: LLM_MODEL=gemma4:12b ...
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from app.evaluation.metrics import grade_answer, has_answer
from app.evaluation.run import fetch_passages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("--document", type=uuid.UUID, required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()

    items = json.loads(args.questions.read_text(encoding="utf-8"))
    correct = unsupported = wrongly_answered = skipped = 0
    seconds: list[float] = []
    model = "?"
    with httpx.Client(base_url=args.api, timeout=600) as client:
        indexed = fetch_passages(client, args.document)
        for item in items:
            sections = item.get("expected_sections")
            if sections and "expected_any" not in item and not has_answer(indexed, sections):
                # The clause has no chunk (empty or redacted in the file): unanswerable here.
                skipped += 1
                print(f"SKIP  {item['question']}  (no chunk matches {sections})")
                continue
            started = time.monotonic()
            response = client.post(
                "/ask", json={"question": item["question"], "document_id": str(args.document)}
            )
            response.raise_for_status()
            took = time.monotonic() - started
            seconds.append(took)
            body = response.json()
            model = body["model"]
            grade = grade_answer(item, body)
            correct += grade.correct
            # Found an answer that no verified quote backs up: a hallucination risk.
            unsupported += grade.found and not grade.supported
            # Answered a question the document cannot answer.
            wrongly_answered += (not item.get("expect_found", True)) and grade.found
            mark = "OK  " if grade.correct else "FAIL"
            flag = "" if not grade.found or grade.supported else "  [UNSUPPORTED]"
            print(f"{mark} {took:5.1f}s  {item['question']}{flag}")
            if not grade.correct or flag:
                print(f"       answer: {body['answer']!r} (found={body['found']})")
                for citation in body["citations"]:
                    print(
                        f"       cites p{citation['page_start']} {citation['section_path']!r} "
                        f"verified={citation['verified']}"
                    )

    n = max(len(items) - skipped, 1)
    print(
        f"\nmodel {model} | {correct}/{n} correct ({correct / n:.0%}, {skipped} skipped) | "
        f"{unsupported} answers without a verified quote | "
        f"{wrongly_answered} answers to unanswerable questions | "
        f"avg {sum(seconds) / n:.1f}s per question"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
