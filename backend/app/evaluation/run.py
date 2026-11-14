"""Measure retrieval quality against a hand-written question set.

Usage (API running, document already indexed):
    uv run python -m app.evaluation.run --document <id> eval/richtech_msa.json
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

import httpx

from app.evaluation.metrics import Passage, first_hit_rank, has_answer, summarize

TOP_K = 5


def fetch_passages(client: httpx.Client, document_id: uuid.UUID) -> list[Passage]:
    """(section_path, text) of every chunk of the document (the API pages its results)."""
    passages: list[Passage] = []
    while True:
        response = client.get(
            f"/documents/{document_id}/chunks", params={"limit": 500, "offset": len(passages)}
        )
        response.raise_for_status()
        page = response.json()
        passages.extend((chunk["section_path"], chunk["text"]) for chunk in page)
        if len(page) < 500:
            return passages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path, help="JSON file with questions")
    parser.add_argument("--document", type=uuid.UUID, required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    ranks: list[int | None] = []
    skipped = 0
    with httpx.Client(base_url=args.api, timeout=60) as client:
        indexed = fetch_passages(client, args.document)
        for item in questions:
            expected_sections = item.get("expected_sections", [])
            expected_text = item.get("expected_text", [])
            if not has_answer(indexed, expected_sections, expected_text):
                # Not a retrieval failure: the expected section has no chunk at all.
                skipped += 1
                wanted = expected_sections or expected_text
                print(f" SKIP  {item['question']}\n       no chunk matches {wanted}")
                continue
            response = client.post(
                "/search",
                json={"query": item["question"], "limit": TOP_K, "document_id": str(args.document)},
            )
            response.raise_for_status()
            hits = response.json()
            sections = [hit["section_path"] for hit in hits]
            passages = [(hit["section_path"], hit["text"]) for hit in hits]
            rank = first_hit_rank(passages, expected_sections, expected_text)
            ranks.append(rank)
            mark = f"#{rank}" if rank else "MISS"
            print(f"{mark:>5}  {item['question']}")
            if rank != 1:
                print(f"       expected {expected_sections or expected_text}, got {sections}")

    summary = summarize(ranks)
    print(
        f"\n{summary.questions} questions ({skipped} skipped: expected section not indexed) | "
        f"hit@1 {summary.hit_at_1:.0%} | "
        f"hit@3 {summary.hit_at_3:.0%} | hit@5 {summary.hit_at_5:.0%} | MRR {summary.mrr:.2f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
