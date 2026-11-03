import pytest

from context_lens.answering import (
    NOT_FOUND_MESSAGE,
    Citation,
    ModelAnswer,
    verify_answer,
)
from context_lens.documents import Document

DOCUMENT = Document(
    id="doc-1",
    filename="notes.txt",
    text=(
        "The cat is orange.\n"
        "The dog is brown.\n"
        "Kočka je oranžová.\n"
        "The bird  is\tblue.\n"
    ),
)
NOT_FOUND = ModelAnswer(status="not_found", answer=NOT_FOUND_MESSAGE, citations=[])


def answered(*citations: Citation) -> ModelAnswer:
    return ModelAnswer(
        status="answered", answer="An answer.", citations=list(citations)
    )


@pytest.mark.parametrize(
    ("start_line", "end_line", "quote"),
    [
        pytest.param(1, 1, "The cat is orange.", id="exact_quote"),
        pytest.param(1, 1, "cat is orange", id="partial_quote"),
        pytest.param(
            1, 2, "The cat is orange. The dog is brown.", id="two_lines_joined_by_space"
        ),
        pytest.param(
            1,
            2,
            "The cat is orange.\nThe dog is brown.",
            id="two_lines_joined_by_newline",
        ),
        pytest.param(1, 2, "orange. The dog", id="partial_quote_across_two_lines"),
        pytest.param(3, 3, "Kočka je oranžová.", id="czech_diacritics"),
        pytest.param(1, 1, "  The   cat\tis orange.\n", id="extra_whitespace_in_quote"),
        pytest.param(4, 4, "The bird is blue.", id="extra_whitespace_in_source"),
    ],
)
def test_verified_citation_keeps_the_answer(
    start_line: int, end_line: int, quote: str
) -> None:
    answer = answered(Citation(start_line=start_line, end_line=end_line, quote=quote))

    assert verify_answer(answer, DOCUMENT) == answer


@pytest.mark.parametrize(
    ("start_line", "end_line", "quote"),
    [
        pytest.param(1, 1, "The cat is purple.", id="fabricated_quote"),
        pytest.param(2, 2, "The cat is orange.", id="wrong_line_numbers"),
        pytest.param(1, 4, "The dog is brown.", id="range_wider_on_both_sides"),
        pytest.param(1, 2, "The cat is orange.", id="range_too_long_at_the_end"),
        pytest.param(1, 2, "The dog is brown.", id="range_too_long_at_the_start"),
        pytest.param(0, 4, "The bird is blue.", id="start_line_zero"),
        pytest.param(4, 5, "The bird is blue.", id="end_line_past_the_end"),
        pytest.param(2, 1, "The cat is orange.", id="start_line_after_end_line"),
        pytest.param(1, 1, "", id="empty_quote"),
        pytest.param(1, 1, " \t\n", id="whitespace_only_quote"),
        pytest.param(1, 1, "the cat is orange.", id="different_letter_case"),
    ],
)
def test_unverifiable_citation_rejects_the_answer(
    start_line: int, end_line: int, quote: str
) -> None:
    answer = answered(Citation(start_line=start_line, end_line=end_line, quote=quote))

    assert verify_answer(answer, DOCUMENT) == NOT_FOUND


def test_answered_without_citations_is_rejected() -> None:
    assert verify_answer(answered(), DOCUMENT) == NOT_FOUND


def test_one_bad_citation_rejects_the_whole_answer() -> None:
    good = Citation(start_line=1, end_line=1, quote="The cat is orange.")
    bad = Citation(start_line=2, end_line=2, quote="The dog is purple.")

    assert verify_answer(answered(good, bad), DOCUMENT) == NOT_FOUND


def test_not_found_from_gemini_gets_the_fixed_message_and_loses_its_citations(
    caplog: pytest.LogCaptureFixture,
) -> None:
    answer = ModelAnswer(
        status="not_found",
        answer="Most cats are tabby, as far as I know.",
        citations=[Citation(start_line=1, end_line=1, quote="The cat is orange.")],
    )

    assert verify_answer(answer, DOCUMENT) == NOT_FOUND
    assert caplog.records == []


def test_rejected_answer_logs_a_warning_without_its_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    answer = ModelAnswer(
        status="answered",
        answer="Private answer.",
        citations=[Citation(start_line=1, end_line=1, quote="Private quote.")],
    )

    verify_answer(answer, DOCUMENT)

    assert [record.levelname for record in caplog.records] == ["WARNING"]
    assert "Private" not in caplog.text
