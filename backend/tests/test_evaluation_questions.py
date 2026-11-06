from collections import Counter
from pathlib import Path

import pytest

from context_lens.evaluation.cases import CATEGORIES, load_question_set

pytestmark = pytest.mark.anyio

EVALS = Path(__file__).resolve().parents[1] / "evals"


async def test_the_question_set_passes_every_check() -> None:
    question_set = await load_question_set(EVALS)

    assert len(question_set.questions) >= 40


async def test_every_category_has_questions() -> None:
    question_set = await load_question_set(EVALS)

    counts = Counter(question.category for question in question_set.questions)
    assert all(counts[category] >= 2 for category in CATEGORIES)


async def test_every_document_is_asked_about() -> None:
    # A document no question uses would be left out of the fingerprint, so a change
    # to it wouldn't show in the results.
    question_set = await load_question_set(EVALS)

    on_disk = {path.name for path in (EVALS / "documents").iterdir()}
    assert set(question_set.documents) == on_disk
