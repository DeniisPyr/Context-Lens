import pytest

from context_lens.evaluation.cases import LineRange, Question
from context_lens.evaluation.matching import contains_phrase
from context_lens.evaluation.scoring import (
    RunRecord,
    RunScore,
    evidence_shown,
    score_run,
    summarize,
)
from context_lens.services.answering import NOT_FOUND_MESSAGE, Citation, ModelAnswer
from context_lens.services.documents import Document

NOT_FOUND = ModelAnswer(status="not_found", answer=NOT_FOUND_MESSAGE, citations=[])


def make_question(**changes: object) -> Question:
    fields = {
        "id": "handbook-remote-days",
        "document": "handbook.md",
        "category": "fact",
        "question": "How many days a week can employees work from home?",
        "facts": [["3 days", "three days"]],
        "evidence": [[42, 43]],
        "forbidden": ["5 days"],
    }
    return Question.model_validate(fields | changes)


UNANSWERABLE = make_question(
    id="handbook-parking", category="missing_related", facts=[], evidence=[]
)


def cite(start_line: int, end_line: int, file: str = "handbook.md") -> Citation:
    return Citation(
        file=file, start_line=start_line, end_line=end_line, quote="A quote."
    )


def answered(text: str, *citations: Citation) -> ModelAnswer:
    return ModelAnswer(status="answered", answer=text, citations=list(citations))


@pytest.mark.parametrize(
    ("text", "phrase"),
    [
        pytest.param("They work 3 days a week.", "3 days", id="exact"),
        pytest.param("THREE DAYS a week", "three days", id="letter_case"),
        pytest.param("3  days\ta week", "3 days", id="whitespace_run_in_text"),
        pytest.param("3 days a week", " 3\t days ", id="whitespace_run_in_phrase"),
        pytest.param("3\ndays", "3 days", id="line_break"),
        pytest.param("3 days", "3 days", id="no_break_space_in_text"),
        pytest.param("3 days", "3 days", id="no_break_space_in_phrase"),
        pytest.param("Kočka je ORANŽOVÁ.", "oranžová", id="czech_diacritics"),
        pytest.param("It costs 1,200 CZK.", "1,200", id="comma_in_a_number"),
        pytest.param("Keep it at 25 °C.", "25 °C", id="degree_sign"),
        pytest.param("(3 days)", "3 days", id="punctuation_around"),
        pytest.param("3 days", "3 days", id="whole_text"),
        pytest.param("Error E37 (column) shown.", "E37 (column)", id="brackets"),
    ],
)
def test_phrase_is_found(text: str, phrase: str) -> None:
    assert contains_phrase(text, phrase)


@pytest.mark.parametrize(
    ("text", "phrase"),
    [
        pytest.param("30 days", "3", id="more_digits_after"),
        pytest.param("13 days", "3", id="more_digits_before"),
        pytest.param("3 days", "3 day", id="part_of_a_word"),
        pytest.param("It costs 11,200 CZK.", "1,200", id="longer_number_before"),
        pytest.param("It costs 1,2000 CZK.", "1,200", id="longer_number_after"),
        pytest.param("Šárka", "árka", id="czech_letter_before"),
        pytest.param("lesů", "les", id="czech_letter_after"),
        pytest.param("oranžová", "oranzova", id="diacritics_matter"),
        pytest.param("Keep it at 25°C.", "25 °C", id="missing_space"),
        pytest.param("3 weeks", "3 days", id="different_words"),
        pytest.param("It costs 1x2 million.", "1.2 million", id="dot_is_a_dot"),
    ],
)
def test_phrase_is_not_found(text: str, phrase: str) -> None:
    assert not contains_phrase(text, phrase)


def test_right_answer_with_its_evidence_is_correct() -> None:
    final = answered("Employees can work three days a week.", cite(42, 43))

    assert score_run(make_question(), final, final) == RunScore(
        correct=True,
        facts_found=[True],
        evidence_cited=[True],
        extra_citations=0,
        forbidden_found=[],
        rejected_by_verifier=False,
    )


@pytest.mark.parametrize(
    ("start_line", "end_line", "cited"),
    [
        pytest.param(42, 43, True, id="same_lines"),
        pytest.param(41, 42, True, id="overlaps_the_start"),
        pytest.param(43, 45, True, id="overlaps_the_end"),
        pytest.param(40, 50, True, id="covers_it"),
        pytest.param(43, 43, True, id="inside_it"),
        pytest.param(40, 41, False, id="just_before"),
        pytest.param(44, 44, False, id="just_after"),
    ],
)
def test_evidence_counts_as_cited_when_a_citation_overlaps_it(
    start_line: int, end_line: int, cited: bool
) -> None:
    final = answered("3 days.", cite(start_line, end_line))

    score = score_run(make_question(), final, final)

    assert score.evidence_cited == [cited]
    assert score.extra_citations == (0 if cited else 1)
    assert score.correct == cited


def test_citation_of_another_file_is_not_evidence_even_on_the_right_lines() -> None:
    final = answered("3 days.", cite(42, 43, "policy.md"))

    score = score_run(make_question(), final, final)

    assert score.evidence_cited == [False]
    assert score.extra_citations == 1
    assert not score.correct


@pytest.mark.parametrize(
    ("file", "cited"),
    [
        pytest.param("R&amp;D &quot;notes&quot;.md", True, id="as_shown"),
        pytest.param('R&D "notes".md', True, id="as_uploaded"),
        pytest.param("R&D &quot;notes&quot;.md", False, id="half_escaped"),
        pytest.param('r&d "notes".md', False, id="other_case"),
    ],
)
def test_citation_counts_when_it_names_the_document_as_shown_or_as_uploaded(
    file: str, cited: bool
) -> None:
    question = make_question(document='R&D "notes".md')
    final = answered("3 days.", cite(42, 43, file))

    score = score_run(question, final, final)

    assert score.evidence_cited == [cited]
    assert score.extra_citations == (0 if cited else 1)


@pytest.mark.parametrize(
    ("citations", "evidence_cited", "extra_citations"),
    [
        pytest.param(
            [cite(42, 43), cite(7, 7, "policy.md")], [True, True], 0, id="both_files"
        ),
        pytest.param(
            [cite(42, 43), cite(7, 7)], [True, False], 1, id="other_lines_in_handbook"
        ),
        pytest.param(
            [cite(42, 43, "policy.md"), cite(7, 7, "policy.md")],
            [False, True],
            1,
            id="handbook_lines_in_policy",
        ),
    ],
)
def test_each_evidence_range_is_checked_against_citations_of_its_own_file(
    citations: list[Citation], evidence_cited: list[bool], extra_citations: int
) -> None:
    question = make_question(
        category="cross_document",
        facts=[["3 days"], ["laptop"]],
        evidence=[[42, 43], ["policy.md", 7, 7]],
    )
    final = answered("3 days, with a laptop.", *citations)

    score = score_run(question, final, final)

    assert score.evidence_cited == evidence_cited
    assert score.extra_citations == extra_citations
    assert score.correct == all(evidence_cited)


def test_extra_citations_are_counted_but_dont_make_the_answer_wrong() -> None:
    final = answered(
        "3 days.", cite(1, 1), cite(42, 43), cite(50, 52), cite(42, 43, "policy.md")
    )

    score = score_run(make_question(), final, final)

    assert score.extra_citations == 3
    assert score.correct


def test_each_evidence_range_must_be_cited() -> None:
    question = make_question(evidence=[[42, 43], [60, 60]])
    final = answered("3 days.", cite(42, 42))

    score = score_run(question, final, final)

    assert score.evidence_cited == [True, False]
    assert not score.correct


def test_each_fact_is_checked_on_its_own() -> None:
    question = make_question(
        category="multi_fact", facts=[["3 days", "three days"], ["Friday"]]
    )
    final = answered("Three days a week.", cite(42, 43))

    score = score_run(question, final, final)

    assert score.facts_found == [True, False]
    assert not score.correct


def test_forbidden_phrase_makes_the_answer_wrong() -> None:
    final = answered("3 days, or 5 days in summer.", cite(42, 43))

    score = score_run(make_question(), final, final)

    assert score.facts_found == [True]
    assert score.forbidden_found == ["5 days"]
    assert not score.correct


def test_answer_without_the_answered_status_is_wrong_whatever_it_says() -> None:
    final = ModelAnswer(status="not_found", answer="3 days.", citations=[cite(42, 43)])

    score = score_run(make_question(), final, final)

    assert score.facts_found == [True]
    assert score.evidence_cited == [True]
    assert not score.correct


def test_not_found_for_an_answerable_question_is_wrong() -> None:
    score = score_run(make_question(), NOT_FOUND, NOT_FOUND)

    assert score == RunScore(
        correct=False,
        facts_found=[False],
        evidence_cited=[False],
        extra_citations=0,
        forbidden_found=[],
        rejected_by_verifier=False,
    )


@pytest.mark.parametrize(
    ("raw", "rejected"),
    [
        pytest.param(answered("3 days.", cite(42, 43)), True, id="answered"),
        pytest.param(NOT_FOUND, False, id="not_found"),
        pytest.param(None, False, id="no_raw_answer"),
    ],
)
def test_verifier_rejected_the_answer_when_gemini_answered_but_the_final_is_not_found(
    raw: ModelAnswer | None, rejected: bool
) -> None:
    score = score_run(make_question(), NOT_FOUND, raw)

    assert score.rejected_by_verifier == rejected
    assert not score.correct


def test_not_found_for_an_unanswerable_question_is_correct() -> None:
    raw = answered("Behind the office.", cite(10, 10))

    score = score_run(UNANSWERABLE, NOT_FOUND, raw)

    assert score.correct
    assert score.rejected_by_verifier


def test_answering_an_unanswerable_question_is_wrong() -> None:
    final = answered("Behind the office.", cite(10, 10))

    score = score_run(UNANSWERABLE, final, final)

    assert score == RunScore(
        correct=False,
        facts_found=[],
        evidence_cited=[],
        extra_citations=1,
        forbidden_found=[],
        rejected_by_verifier=False,
    )


# Ten lines, of which line 5 is blank.
NOTES = Document(
    id="notes.md",
    filename="notes.md",
    text="".join(f"Line {n}.\n" if n != 5 else "\n" for n in range(1, 11)),
)
OTHER = Document(id="other.md", filename="other.md", text="Other.\n" * 10)


@pytest.mark.parametrize(
    ("excerpts", "shown"),
    [
        pytest.param([("notes.md", 1, 10)], True, id="inside_an_excerpt"),
        pytest.param([("notes.md", 3, 4)], True, id="exactly"),
        pytest.param(
            [("notes.md", 4, 6), ("notes.md", 1, 3)], True, id="across_two_excerpts"
        ),
        pytest.param([("notes.md", 1, 3)], False, id="only_its_start"),
        pytest.param([("notes.md", 4, 10)], False, id="only_its_end"),
        pytest.param([("notes.md", 1, 2), ("notes.md", 5, 10)], False, id="all_but_it"),
        pytest.param([("other.md", 1, 10)], False, id="another_file"),
        pytest.param([], False, id="nothing_shown"),
    ],
)
def test_evidence_was_shown_when_every_line_of_it_was(
    excerpts: list[tuple[str, int, int]], shown: bool
) -> None:
    evidence = [LineRange("notes.md", 3, 4)]
    shown_lines = [LineRange(*lines) for lines in excerpts]

    assert evidence_shown(evidence, shown_lines, {"notes.md": NOTES}) == [shown]


@pytest.mark.parametrize(
    ("excerpts", "shown"),
    [
        pytest.param([("notes.md", 1, 4), ("notes.md", 6, 9)], True, id="around_it"),
        pytest.param([("notes.md", 1, 4)], False, id="only_before_it"),
    ],
)
def test_blank_line_in_evidence_needs_no_showing(
    excerpts: list[tuple[str, int, int]], shown: bool
) -> None:
    evidence = [LineRange("notes.md", 4, 6)]
    shown_lines = [LineRange(*lines) for lines in excerpts]

    assert evidence_shown(evidence, shown_lines, {"notes.md": NOTES}) == [shown]


def test_each_evidence_range_is_shown_or_not_on_its_own() -> None:
    evidence = [LineRange("notes.md", 3, 4), LineRange("other.md", 7, 7)]
    excerpts = [LineRange("other.md", 1, 10), LineRange("notes.md", 4, 6)]
    documents = {"notes.md": NOTES, "other.md": OTHER}

    assert evidence_shown(evidence, excerpts, documents) == [False, True]


def make_record(
    question: Question,
    final: ModelAnswer | None,
    raw: ModelAnswer | None = None,
    *,
    repeat: int = 1,
    seconds: float = 1.0,
    tokens: tuple[int, int, int] = (0, 0, 0),
    shown: list[bool] | None = None,
) -> RunRecord:
    # No final answer stands for a run that ended in a Gemini error.
    raw = final if raw is None else raw
    input_tokens, output_tokens, thought_tokens = tokens
    if final is not None and shown is None:
        # Unless a test says otherwise, Gemini was shown all the evidence.
        shown = [True] * len(question.evidence)
    return RunRecord(
        question_id=question.id,
        repeat=repeat,
        category=question.category,
        document=question.document,
        question=question.question,
        facts=question.facts,
        evidence=question.evidence,
        status=None if final is None else final.status,
        answer=None if final is None else final.answer,
        citations=[] if final is None else final.citations,
        raw_status=None if raw is None else raw.status,
        raw_citations=None,
        excerpts=[],
        evidence_shown=shown,
        seconds=seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thought_tokens=thought_tokens,
        embedded_characters=0,
        error="GeminiUnavailableError" if final is None else None,
        score=None if final is None else score_run(question, final, raw),
    )


def test_summary_of_no_runs_has_no_rates() -> None:
    no_rate = {"rate": None, "count": 0, "of": 0}

    assert summarize([]) == {
        "questions": 0,
        "runs": 0,
        "errors": 0,
        "correct": no_rate,
        "answerable_runs": 0,
        "answer_accuracy": no_rate,
        "citation_accuracy": no_rate,
        "evidence_shown": no_rate,
        "false_not_found_rate": no_rate,
        "unanswerable_runs": 0,
        "not_found_accuracy": no_rate,
        "rejected_by_verifier": no_rate,
        "median_seconds": None,
        "p95_seconds": None,
        "max_seconds": None,
        "mean_input_tokens": None,
        "mean_output_tokens": None,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


def test_summary_counts_each_kind_of_outcome() -> None:
    remote_days = make_question()
    office = make_question(id="handbook-office", facts=[["8:00"]], evidence=[[7, 7]])
    unrelated = make_question(
        id="handbook-ceo", category="missing_unrelated", facts=[], evidence=[]
    )
    records = [
        # Right.
        make_record(remote_days, answered("3 days.", cite(42, 43)), seconds=1),
        # Answer wrong, citation right.
        make_record(
            remote_days, answered("5 days.", cite(42, 43)), repeat=2, seconds=2
        ),
        # Rejected by the verifier, so a false not found.
        make_record(office, NOT_FOUND, answered("8:00.", cite(7, 7)), seconds=3),
        # Answer right, citation wrong.
        make_record(office, answered("8:00.", cite(1, 1)), repeat=2, seconds=4),
        make_record(UNANSWERABLE, NOT_FOUND, seconds=5),
        make_record(unrelated, answered("Jana.", cite(1, 1)), seconds=6),
        make_record(unrelated, None, repeat=2, seconds=60),
    ]

    summary = summarize(records)

    assert summary["questions"] == 4
    assert summary["runs"] == 7
    assert summary["errors"] == 1
    assert summary["correct"] == {"rate": 2 / 6, "count": 2, "of": 6}
    assert summary["answerable_runs"] == 4
    assert summary["answer_accuracy"] == {"rate": 0.5, "count": 2, "of": 4}
    assert summary["citation_accuracy"] == {"rate": 0.5, "count": 2, "of": 4}
    assert summary["false_not_found_rate"] == {"rate": 0.25, "count": 1, "of": 4}
    assert summary["unanswerable_runs"] == 2
    assert summary["not_found_accuracy"] == {"rate": 0.5, "count": 1, "of": 2}
    assert summary["rejected_by_verifier"] == {"rate": 1 / 6, "count": 1, "of": 6}


def test_evidence_shown_counts_answerable_runs_shown_all_their_evidence() -> None:
    question = make_question(
        category="multi_fact",
        facts=[["3 days"], ["Friday"]],
        evidence=[[42, 43], [50, 50]],
    )
    records = [
        make_record(question, NOT_FOUND, shown=[True, True]),
        make_record(question, NOT_FOUND, repeat=2, shown=[True, False]),
        make_record(question, NOT_FOUND, repeat=3, shown=[False, False]),
        make_record(question, None, repeat=4),
        make_record(UNANSWERABLE, NOT_FOUND),
    ]

    summary = summarize(records)

    assert summary["evidence_shown"] == {"rate": 1 / 3, "count": 1, "of": 3}


def test_answer_with_a_forbidden_phrase_counts_against_answer_accuracy() -> None:
    final = answered("3 days, or 5 days in summer.", cite(42, 43))

    summary = summarize([make_record(make_question(), final)])

    assert summary["answer_accuracy"] == {"rate": 0.0, "count": 0, "of": 1}
    assert summary["citation_accuracy"] == {"rate": 1.0, "count": 1, "of": 1}


def test_rates_without_runs_to_count_are_none() -> None:
    summary = summarize([make_record(UNANSWERABLE, NOT_FOUND)])

    assert summary["answer_accuracy"] == {"rate": None, "count": 0, "of": 0}
    assert summary["not_found_accuracy"] == {"rate": 1.0, "count": 1, "of": 1}


def test_runs_that_ended_in_an_error_are_left_out_of_the_rates() -> None:
    records = [make_record(make_question(), None), make_record(UNANSWERABLE, None)]

    summary = summarize(records)

    assert summary["runs"] == 2
    assert summary["errors"] == 2
    assert summary["correct"] == {"rate": None, "count": 0, "of": 0}
    assert summary["answerable_runs"] == 0
    assert summary["median_seconds"] is None


def test_timings_use_the_median_and_the_nearest_rank_p95() -> None:
    records = [
        make_record(UNANSWERABLE, NOT_FOUND, repeat=seconds, seconds=seconds)
        for seconds in [20, *range(1, 20)]
    ]
    records.append(make_record(UNANSWERABLE, None, repeat=21, seconds=600))

    summary = summarize(records)

    assert summary["median_seconds"] == 10.5
    assert summary["p95_seconds"] == 19
    assert summary["max_seconds"] == 20


def test_output_tokens_include_thinking() -> None:
    records = [
        make_record(UNANSWERABLE, NOT_FOUND, tokens=(100, 10, 20)),
        make_record(UNANSWERABLE, NOT_FOUND, repeat=2, tokens=(300, 30, 0)),
    ]

    summary = summarize(records)

    assert summary["mean_input_tokens"] == 200
    assert summary["mean_output_tokens"] == 30
    assert summary["total_input_tokens"] == 400
    assert summary["total_output_tokens"] == 60
