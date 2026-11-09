import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from context_lens.evaluation.cases import Question, QuestionSet
from context_lens.evaluation.compare import main
from context_lens.evaluation.dataset import IndexInfo
from context_lens.evaluation.report import Report, build_report
from context_lens.evaluation.scoring import RunRecord, score_run
from context_lens.services.answering import Citation, ModelAnswer
from context_lens.services.documents import Document

HANDBOOK = Document(
    id="handbook.md",
    filename="handbook.md",
    text="# Handbook\nEmployees can work from home 3 days a week.\n",
)
REMOTE_DAYS = Question(
    id="remote-days",
    document="handbook.md",
    category="fact",
    question="How many days a week can employees work from home?",
    facts=[["3 days"]],
    evidence=[[2, 2]],
)
OFFICE = REMOTE_DAYS.model_copy(update={"id": "office", "question": "When?"})
PARKING = Question(
    id="parking",
    document="handbook.md",
    category="missing_related",
    question="Where can employees park?",
)
RIGHT = ModelAnswer(
    status="answered",
    answer="3 days.",
    citations=[Citation(file="handbook.md", start_line=2, end_line=2, quote="3 days")],
)
NOT_FOUND = ModelAnswer(status="not_found", answer="Not there.", citations=[])
# Working from home and in the office have different rules.
WHERE_TO_WORK = Question(
    id="where-to-work",
    document="handbook.md",
    category="clarify",
    question="How many days a week do employees work?",
    reply="At home.",
    facts=[["3 days"]],
    evidence=[[2, 2]],
    cases=[[1, 2]],
)
AT_HOME_OR_IN_THE_OFFICE = ModelAnswer(
    status="needs_clarification",
    answer="At home or in the office?",
    citations=[Citation(file="handbook.md", start_line=2, end_line=2, quote="home")],
)


def run(
    question: Question,
    final: ModelAnswer,
    repeat: int = 1,
    shown: bool = True,
    asked: ModelAnswer | None = None,
) -> RunRecord:
    # asked is the clarifying question Gemini asked first, if it did.
    return RunRecord(
        question_id=question.id,
        repeat=repeat,
        category=question.category,
        document=question.document,
        question=question.question,
        facts=question.facts,
        evidence=question.evidence,
        cases=question.cases,
        status=final.status,
        answer=final.answer,
        citations=final.citations,
        raw_status=final.status,
        raw_citations=None,
        clarification=None if asked is None else asked.answer,
        clarification_citations=[] if asked is None else asked.citations,
        reply=None if asked is None else question.reply,
        excerpts=[],
        evidence_shown=[shown] * len(question.evidence),
        cases_shown=[shown] * len(question.cases),
        seconds=2.0,
        input_tokens=100,
        output_tokens=10,
        thought_tokens=0,
        embedded_characters=0,
        error=None,
        score=score_run(question, final, final, asked=asked is not None),
    )


def make_report(
    records: list[RunRecord],
    *,
    method: str = "rag",
    model: str = "test-model",
    repeats: int = 1,
    fingerprint: str = "sha256:test",
) -> Report:
    questions = list({record.question_id: record for record in records})
    question_set = QuestionSet(
        [REMOTE_DAYS] * len(questions), {"handbook.md": HANDBOOK}, fingerprint
    )
    rag = method == "rag"
    return build_report(
        records,
        question_set,
        method=method,
        model=model,
        chunks_per_question=8 if rag else None,
        index=IndexInfo(chunks=2, embedded_characters=90, seconds=0.5) if rag else None,
        started_at=datetime(2026, 11, 8, 10, 0, tzinfo=UTC),
        duration_seconds=10.0,
        repeats=repeats,
        concurrency=1,
    )


def save(path: Path, report: Report) -> str:
    path.write_text(json.dumps(report))
    return str(path)


@pytest.fixture
def reports(tmp_path: Path) -> tuple[str, str]:
    rag = make_report(
        [
            run(REMOTE_DAYS, NOT_FOUND, shown=False),
            run(OFFICE, RIGHT),
            run(PARKING, NOT_FOUND),
        ]
    )
    whole = make_report(
        [run(REMOTE_DAYS, RIGHT), run(OFFICE, RIGHT), run(PARKING, NOT_FOUND)],
        method="whole_document",
    )
    return save(tmp_path / "rag.json", rag), save(tmp_path / "whole.json", whole)


def compare(capsys: pytest.CaptureFixture[str], *argv: str) -> list[str]:
    assert main(list(argv)) == 0
    return capsys.readouterr().out.splitlines()


def test_header_shows_each_reports_method_model_repeats_and_chunks(
    reports: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rag, whole = reports

    lines = compare(capsys, rag, whole)

    assert lines[:11] == [
        "# Answer quality compared: rag and whole_document",
        "",
        "3 questions about 1 document (set sha256:test).",
        "",
        "|  | rag | whole_document |",
        "| --- | --- | --- |",
        f"| Report | {rag} | {whole} |",
        "| Method | rag | whole_document |",
        "| Model | test-model | test-model |",
        "| Repeats | 1 | 1 |",
        "| Chunks per question | 8 | n/a |",
    ]


def test_summary_puts_each_measure_of_both_side_by_side(
    reports: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    lines = compare(capsys, *reports)

    assert "| Measure | rag | whole_document |" in lines
    assert "| Correct | 67% (2/3) | 100% (3/3) |" in lines
    assert "| Answer accuracy | 50% (1/2) | 100% (2/2) |" in lines
    assert "| Evidence shown to Gemini | 50% (1/2) | 100% (2/2) |" in lines
    assert "| False not found | 50% (1/2) | 0% (0/2) |" in lines
    assert "| Median seconds | 2.0 | 2.0 |" in lines


def test_categories_show_correct_and_answer_accuracy_for_both(
    reports: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    lines = compare(capsys, *reports)

    header = (
        "| Category | Correct, rag | Correct, whole_document | Answer accuracy, rag "
        "| Answer accuracy, whole_document | Clarified, rag | Clarified, whole_document "
        "| Needless clarification, rag | Needless clarification, whole_document |"
    )
    fact = (
        "| fact | 50% (1/2) | 100% (2/2) | 50% (1/2) | 100% (2/2) | n/a | n/a "
        "| 0% (0/2) | 0% (0/2) |"
    )
    missing_related = (
        "| missing_related | 100% (1/1) | 100% (1/1) | n/a | n/a | n/a | n/a "
        "| 0% (0/1) | 0% (0/1) |"
    )
    assert lines[lines.index("## By category") + 2 :][:4] == [
        header,
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        fact,
        missing_related,
    ]


def test_category_in_only_one_report_is_not_applicable_in_the_other(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = save(tmp_path / "a.json", make_report([run(REMOTE_DAYS, RIGHT)]))
    second = save(tmp_path / "b.json", make_report([run(PARKING, NOT_FOUND)]))

    lines = compare(capsys, first, second)

    assert (
        "| fact | 100% (1/1) | n/a | 100% (1/1) | n/a | n/a | n/a | 0% (0/1) | n/a |"
        in lines
    )
    assert (
        "| missing_related | n/a | 100% (1/1) | n/a | n/a | n/a | n/a | n/a | 0% (0/1) |"
        in lines
    )


def test_clarifying_questions_are_compared_in_the_summary_and_by_category(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    which = AT_HOME_OR_IN_THE_OFFICE
    asks = make_report(
        [
            run(WHERE_TO_WORK, RIGHT, asked=which),
            run(REMOTE_DAYS, which, asked=which),
        ]
    )
    guesses = make_report([run(WHERE_TO_WORK, RIGHT), run(REMOTE_DAYS, RIGHT)])

    lines = compare(
        capsys, save(tmp_path / "a.json", asks), save(tmp_path / "b.json", guesses)
    )

    assert "| Clarified | 100% (1/1) | 0% (0/1) |" in lines
    assert "| Needless clarification | 100% (1/1) | 0% (0/1) |" in lines
    assert (
        "| clarify | 100% (1/1) | 0% (0/1) | n/a | n/a | 100% (1/1) | 0% (0/1) | n/a "
        "| n/a |"
    ) in lines
    heading = lines.index("## Questions with different results")
    assert lines[heading + 2 :] == [
        "- `where-to-work`: A 1/1, B 0/1",
        "  - B #1: didn't ask which situation applies",
        "- `remote-days`: A 0/1, B 1/1",
        '  - A #1: needed no clarifying question; asked "At home or in the office?"',
    ]


def test_differences_list_each_question_with_the_worse_sides_reasons(
    reports: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rag, whole = reports

    for first, second in ((rag, whole), (whole, rag)):
        lines = compare(capsys, first, second)
        heading = lines.index("## Questions with different results")
        counts = (
            "rag 0/1, whole_document 1/1"
            if first == rag
            else "whole_document 1/1, rag 0/1"
        )
        reasons = "said not found; evidence handbook.md line 2 not shown to Gemini"
        assert lines[heading + 2 :] == [
            f"- `remote-days`: {counts}",
            f"  - rag #1: {reasons}",
        ]


def test_reports_with_the_same_results_have_no_differences(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [run(REMOTE_DAYS, RIGHT), run(PARKING, NOT_FOUND)]
    first = save(tmp_path / "a.json", make_report(records))
    second = save(tmp_path / "b.json", make_report(records, model="other-model"))

    lines = compare(capsys, first, second)

    assert lines[0] == "# Answer quality compared: A and B"
    assert "| Model | test-model | other-model |" in lines
    assert lines[-3:] == ["## Questions with different results", "", "None."]


def test_reports_with_different_repeats_compare_the_share_of_correct_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    once = make_report([run(REMOTE_DAYS, RIGHT)])
    three_times = make_report(
        [
            run(REMOTE_DAYS, RIGHT),
            run(REMOTE_DAYS, RIGHT, repeat=2),
            run(REMOTE_DAYS, NOT_FOUND, repeat=3),
        ],
        repeats=3,
    )
    all_three = make_report(
        [run(REMOTE_DAYS, RIGHT, repeat=repeat) for repeat in (1, 2, 3)], repeats=3
    )
    first = save(tmp_path / "once.json", once)

    lines = compare(capsys, first, save(tmp_path / "three.json", three_times))
    same = compare(capsys, first, save(tmp_path / "all.json", all_three))

    assert "| Repeats | 1 | 3 |" in lines
    assert lines[-2:] == ["- `remote-days`: A 1/1, B 2/3", "  - B #3: said not found"]
    assert same[-1] == "None."


def test_output_writes_the_markdown_it_prints(
    reports: tuple[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "out" / "comparison.md"

    exit_code = main([*reports, "--output", str(path)])

    assert exit_code == 0
    output = capsys.readouterr()
    assert path.read_text() == output.out
    assert output.err == f"Wrote {path}.\n"


def test_reports_of_different_question_sets_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = save(tmp_path / "a.json", make_report([run(REMOTE_DAYS, RIGHT)]))
    other = make_report([run(REMOTE_DAYS, RIGHT)], fingerprint="sha256:other")
    second = save(tmp_path / "b.json", other)
    path = tmp_path / "comparison.md"

    exit_code = main([first, second, "--output", str(path)])

    assert exit_code == 2
    output = capsys.readouterr()
    assert output.err == (
        f"{first} and {second} are of different question sets, so they can't be "
        "compared.\n"
    )
    assert output.out == ""
    assert not path.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        pytest.param(None, "Can't read", id="missing"),
        pytest.param("{not json", "is not JSON", id="not_json"),
        pytest.param(
            '{"method": "whole_document"}',
            "is not an evaluation report in the current format: model: Field required.",
            id="not_a_report",
        ),
    ],
)
def test_unreadable_report_is_an_error_naming_it(
    reports: tuple[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str | None,
    message: str,
) -> None:
    path = tmp_path / "broken.json"
    if content is not None:
        path.write_text(content)

    exit_code = main([reports[0], str(path)])

    assert exit_code == 2
    error = capsys.readouterr().err
    assert error.count("\n") == 1
    assert str(path) in error
    assert message in error


def test_report_in_an_older_format_is_an_error(
    reports: tuple[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = json.loads(Path(reports[1]).read_text())
    for run_data in old["runs"]:
        run_data["evidence"] = [[2, 2]]
    path = save(tmp_path / "old.json", old)

    exit_code = main([reports[0], path])

    assert exit_code == 2
    assert capsys.readouterr().err.startswith(
        f"{path} is not an evaluation report in the current format: "
        "runs.0.evidence.0.0: Input should be a valid string."
    )


def test_report_from_before_clarifying_questions_is_an_error(
    reports: tuple[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = json.loads(Path(reports[1]).read_text())
    new_keys = ("clarify_runs", "clarified", "needless_clarification")
    for summary in [old["summary"], *old["by_category"].values()]:
        for key in new_keys:
            del summary[key]
    for run_data in old["runs"]:
        for key in ("cases", "clarification", "clarification_citations", "reply"):
            del run_data[key]
        del run_data["cases_shown"]
    path = save(tmp_path / "old.json", old)

    exit_code = main([reports[0], path])

    assert exit_code == 2
    assert capsys.readouterr().err == (
        f"{path} is not an evaluation report in the current format: "
        "summary.clarify_runs: Field required.\n"
    )


def test_output_that_isnt_markdown_is_a_usage_error(
    reports: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([*reports, "--output", "rag.json"])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.endswith(
        "error: --output is the markdown comparison, so it must end in .md\n"
    )
