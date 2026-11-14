from app.parsing.base import Block
from app.parsing.toc import strip_table_of_contents


def blocks(*lines: str) -> list[Block]:
    return [Block(line, 1) for line in lines]


def test_table_of_contents_run_is_removed() -> None:
    toc = [
        "1. INTRODUCTION. 5",
        "1.1 Purpose. 5",
        "2. DEFINITIONS. 6",
        "2.1 Interpretation. 6",
        "3. FEES. 7",
        "3.1 Payment. 8",
        "3.2 Taxes. 8",
    ]
    result = strip_table_of_contents(
        blocks("TABLE OF CONTENTS", *toc, "1. INTRODUCTION.", "Real text.")
    )

    assert [b.text for b in result] == ["TABLE OF CONTENTS", "1. INTRODUCTION.", "Real text."]


def test_dot_leader_entries_are_recognised_without_section_numbers() -> None:
    toc = [f"Chapter title {n} ........ {n + 3}" for n in range(8)]
    assert strip_table_of_contents(blocks(*toc, "Body text.")) == blocks("Body text.")


def test_a_few_numbered_lines_ending_with_a_number_are_kept() -> None:
    lines = ["1. Payment within 30", "2. Delivery within 14", "3. Warranty of 12"]
    assert strip_table_of_contents(blocks(*lines)) == blocks(*lines)


def test_lines_whose_numbers_go_down_are_not_a_table_of_contents() -> None:
    # Page numbers in a real table of contents never decrease; these look like prices.
    lines = [
        "1 Widget 900",
        "2 Gadget 700",
        "3 Gizmo 500",
        "4 Doohickey 300",
        "5 Thing 200",
        "6 Item 100",
    ]
    assert strip_table_of_contents(blocks(*lines)) == blocks(*lines)
