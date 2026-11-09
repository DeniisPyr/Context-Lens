from collections import Counter
from pathlib import Path

from context_lens.evaluation.cases import CATEGORIES, load_question_set

EVALS = Path(__file__).resolve().parents[1] / "evals"


def test_the_question_set_passes_every_check() -> None:
    question_set = load_question_set(EVALS)

    assert len(question_set.questions) >= 40


def test_every_category_has_questions() -> None:
    question_set = load_question_set(EVALS)

    counts = Counter(question.category for question in question_set.questions)
    assert all(counts[category] >= 2 for category in CATEGORIES)
