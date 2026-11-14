import pytest

from app.evaluation.metrics import (
    first_hit_rank,
    grade_answer,
    has_answer,
    section_matches,
    summarize,
)


@pytest.mark.parametrize(
    ("section", "expected", "matches"),
    [
        ("6.4.1 Invoices.", "6.4.1", True),
        ("6.4.1 Invoices.", "6.4", True),  # a sub-section of an acceptable section
        ("6.4.10 Something.", "6.4.1", False),  # not a string prefix match
        ("16.12 Governing Law; Venue.", "16.1", False),
        ("12. INSURANCE COVERAGE.", "12", True),
        ("Article 6 (Charges and Payment).", "6", False),
        (None, "6", False),
    ],
)
def test_section_matches(section: str | None, expected: str, matches: bool) -> None:
    assert section_matches(section, expected) is matches


def test_first_hit_rank() -> None:
    passages = [("1.1 A", "x"), ("2.3 B", "y"), ("2.3.1 C", "z")]
    assert first_hit_rank(passages, ["2.3"]) == 2
    assert first_hit_rank(passages, ["9", "1"]) == 1
    assert first_hit_rank(passages, ["7"]) is None


def test_a_snippet_can_identify_the_answer_when_there_are_no_sections() -> None:
    passages = [(None, "Payment is due\nwithin 30 days."), (None, "Either party may terminate")]

    # Line breaks and case do not matter: PDF text is wrapped arbitrarily.
    assert first_hit_rank(passages, [], ["PAYMENT is due within 30 days"]) == 1
    assert first_hit_rank(passages, [], ["may terminate"]) == 2
    assert first_hit_rank(passages, [], ["governing law"]) is None


def test_summary() -> None:
    summary = summarize([1, 2, None, 5])

    assert summary.questions == 4
    assert summary.hit_at_1 == 0.25
    assert summary.hit_at_3 == 0.5
    assert summary.hit_at_5 == 0.75
    assert summary.mrr == pytest.approx((1 + 0.5 + 0 + 0.2) / 4)


def test_summary_of_nothing() -> None:
    assert summarize([]).mrr == 0.0


def test_has_answer_requires_an_indexed_chunk_in_the_expected_section() -> None:
    indexed = [("6.4.7 Currency.", "a"), ("8.1 Terms.", "b"), (None, "free text")]
    assert has_answer(indexed, ["8.1.2", "8.1"])
    assert not has_answer(indexed, ["14.2"])  # an empty (redacted) section has no chunk
    assert has_answer(indexed, [], ["free text"])


def reply(answer: str, found: bool = True, supported: bool = True) -> dict:
    return {"answer": answer, "found": found, "supported": supported}


def test_grading_an_answer_that_contains_an_expected_snippet() -> None:
    item = {"expected_any": ["ten (10) business days", "10 business days"]}

    assert grade_answer(item, reply("Ten (10)  BUSINESS days of written notice.")).correct
    assert grade_answer(item, reply("10 business days")).correct
    assert not grade_answer(item, reply("Thirty days.")).correct
    # An answer that is not "found" is never correct, even if the text happens to match.
    assert not grade_answer(item, reply("10 business days", found=False)).correct


def test_grading_an_unanswerable_question() -> None:
    item = {"expect_found": False}

    assert grade_answer(item, reply("", found=False, supported=False)).correct
    assert not grade_answer(item, reply("A 5% penalty.")).correct  # made something up


def test_grade_reports_support() -> None:
    item = {"expected_any": ["x"]}
    assert grade_answer(item, reply("x", supported=False)).supported is False


def test_grading_by_the_clause_of_the_verified_citation() -> None:
    item = {"expected_sections": ["8.1.2", "8.1"]}

    def with_citation(section: str, verified: bool = True) -> dict:
        body = reply("Customer owns the work products.")
        body["citations"] = [{"section_path": section, "verified": verified}]
        return body

    assert grade_answer(item, with_citation("8.1.2 Ownership.")).correct
    assert not grade_answer(item, with_citation("8.2 Licence.")).correct
    # A quote that was not found in the chunk proves nothing.
    assert not grade_answer(item, with_citation("8.1.2 Ownership.", verified=False)).correct
