"""F12: the decision memo is deterministic, short, complete, and every number in it comes from outputs."""

import json
import re
from pathlib import Path

from sifpa import memo

ROOT = Path(__file__).resolve().parents[1]
# numbers that are part of the framing, not model outputs (dates, plan years, statutory facts, page refs)
ALLOWED = {"2026", "2027", "2028", "2019", "2024", "2025", "11", "02", "30", "09", "8", "6", "5", "10", "2", "3",
           "2,000", "1", "835", "100"}  # 100 = "per 100k" unit


def test_memo_is_reproducible_from_outputs():
    text, numbers = memo.build()
    assert (ROOT / "docs/MEMO.md").read_text() == text
    assert json.loads((ROOT / "outputs/memo_numbers.json").read_text()) == numbers


def test_memo_has_decision_structure_and_length():
    text = (ROOT / "docs/MEMO.md").read_text()
    for heading in ("## Recommendation", "## Risks", "## What would change this recommendation"):
        assert heading in text
    assert len(text.split()) <= 1000  # roughly two pages


def test_every_number_in_memo_comes_from_the_numbers_dict():
    text, numbers = memo.build()
    allowed_tokens = set(ALLOWED)
    for v in numbers.values():
        allowed_tokens |= set(re.findall(r"\d[\d,.]*", v))
    for tok in re.findall(r"\d[\d,.]*\d|\d", text):
        tok = tok.rstrip(".,")
        assert tok in allowed_tokens, f"memo number {tok!r} is not traceable to outputs"


def test_memo_draws_no_conclusion_from_synthetic_data():
    text = (ROOT / "docs/MEMO.md").read_text().lower()
    assert "synthetic" not in text and "denial" not in text and "days in ar" not in text
