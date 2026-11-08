import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from context_lens.clients.gemini import GeminiUnavailableError, TokenUsage
from context_lens.evaluation.cases import Question, QuestionSet
from context_lens.evaluation.report import Report, build_report, render_markdown
from context_lens.evaluation.runner import run_questions
from context_lens.evaluation.scoring import RunRecord, summarize
from context_lens.services.answering import Citation, ModelAnswer
from context_lens.services.documents import Document

pytestmark = pytest.mark.anyio

HANDBOOK = Document(
    id="handbook.md",
    filename="handbook.md",
    text=(
        "# Handbook\n"
        "Employees can work from home 3 days a week.\n"
        "The office opens at 8:00.\n"
    ),
)
RULES = Document(id="rules.md", filename="rules.md", text="Dress well.\n")
STARTED_AT = datetime(2026, 11, 6, 9, 30, tzinfo=UTC)

type Script = ModelAnswer | Exception


def make_question(question_id: str, **changes: object) -> Question:
    fields = {
        "id": question_id,
        "document": "handbook.md",
        "category": "fact",
        "question": f"Question {question_id}?",
        "facts": [["3 days", "three days"]],
        "evidence": [[2, 2]],
        "forbidden": ["5 days"],
    }
    return Question.model_validate(fields | changes)


def unanswerable(question_id: str, **changes: object) -> Question:
    return make_question(
        question_id, category="missing_related", facts=[], evidence=[], **changes
    )


def answered(
    text: str, line: int, quote: str, file: str = "handbook.md"
) -> ModelAnswer:
    citation = Citation(file=file, start_line=line, end_line=line, quote=quote)
    return ModelAnswer(status="answered", answer=text, citations=[citation])


RIGHT = answered("Employees can work from home 3 days a week.", 2, "3 days a week")
NOT_FOUND = ModelAnswer(status="not_found", answer="Not there.", citations=[])


class ScriptedGemini:
    def __init__(self, scripts: dict[str, Script]) -> None:
        self.scripts = scripts

    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]:
        script = self.scripts[prompt.rpartition("Question: ")[2]]
        if isinstance(script, Exception):
            raise script
        usage = TokenUsage(input_tokens=1000, output_tokens=200, thought_tokens=34)
        return response_model.model_validate(script.model_dump()), usage


async def report_for(*runs: tuple[Question, Script]) -> Report:
    questions = [question for question, _ in runs]
    question_set = QuestionSet(
        questions, {"handbook.md": HANDBOOK, "rules.md": RULES}, "sha256:test"
    )
    gemini = ScriptedGemini({question.question: script for question, script in runs})
    records = await run_questions(question_set, gemini)
    return build_report(
        records,
        question_set,
        model="test-model",
        started_at=STARTED_AT,
        duration_seconds=12.345,
        repeats=1,
        concurrency=1,
    )


async def test_report_has_the_settings_summaries_and_every_run() -> None:
    report = await report_for(
        (unanswerable("parking"), NOT_FOUND),
        (make_question("remote-days"), RIGHT),
        (
            unanswerable("dress-code", document="rules.md"),
            answered("Dress well.", 1, "Dress well.", "rules.md"),
        ),
    )

    summaries = ("summary", "by_category", "by_document", "runs")
    assert {key: value for key, value in report.items() if key not in summaries} == {
        "method": "whole_document",
        "model": "test-model",
        "started_at": "2026-11-06T09:30:00+00:00",
        "duration_seconds": 12.345,
        "repeats": 1,
        "concurrency": 1,
        "question_set": {
            "questions": 3,
            "documents": 2,
            "fingerprint": "sha256:test",
        },
    }
    assert [run["question_id"] for run in report["runs"]] == [
        "parking",
        "remote-days",
        "dress-code",
    ]
    assert report["summary"]["runs"] == 3
    assert report["summary"]["correct"] == {"rate": 2 / 3, "count": 2, "of": 3}
    assert list(report["by_category"]) == ["fact", "missing_related"]
    assert list(report["by_document"]) == ["handbook.md", "rules.md"]


async def test_report_survives_a_trip_through_json() -> None:
    report = await report_for((make_question("remote-days"), RIGHT))

    loaded = json.loads(json.dumps(report))

    assert loaded == report
    assert render_markdown(loaded) == render_markdown(report)


async def test_each_group_summarizes_its_own_runs() -> None:
    report = await report_for(
        (make_question("remote-days"), RIGHT),
        (unanswerable("parking"), RIGHT),
        (unanswerable("dress-code", document="rules.md"), NOT_FOUND),
    )
    remote_days, parking, dress_code = [
        RunRecord.model_validate(run) for run in report["runs"]
    ]

    assert report["by_category"] == {
        "fact": summarize([remote_days]),
        "missing_related": summarize([parking, dress_code]),
    }
    assert report["by_document"] == {
        "handbook.md": summarize([remote_days, parking]),
        "rules.md": summarize([dress_code]),
    }


async def test_markdown_starts_with_the_method_model_and_settings() -> None:
    report = await report_for((make_question("remote-days"), RIGHT))

    heading, blank, about, *_ = render_markdown(report).splitlines()

    assert heading == "# Answer quality: whole_document, test-model"
    assert blank == ""
    assert about == (
        "1 question about 2 documents (set sha256:test), 1 repeat, concurrency 1, "
        "started 2026-11-06T09:30:00+00:00, took 12.3 s."
    )


async def test_markdown_shows_rates_with_their_counts_and_rounds_numbers() -> None:
    report = await report_for(
        (make_question("remote-days"), RIGHT),
        (make_question("office"), NOT_FOUND),
        (unanswerable("parking"), NOT_FOUND),
    )
    report["summary"]["median_seconds"] = 3.26
    report["summary"]["mean_input_tokens"] = 1234.6

    markdown = render_markdown(report)

    assert "| Correct | 67% (2/3) |" in markdown
    assert "| Answer accuracy | 50% (1/2) |" in markdown
    assert "| False not found | 50% (1/2) |" in markdown
    assert "| Not found accuracy | 100% (1/1) |" in markdown
    assert "| Median seconds | 3.3 |" in markdown
    assert "| Mean input tokens | 1235 |" in markdown
    assert "| Mean output tokens, with thinking | 234 |" in markdown
    assert "| Total output tokens, with thinking | 702 |" in markdown


async def test_markdown_has_a_row_for_each_category_and_document() -> None:
    report = await report_for(
        (make_question("remote-days"), RIGHT),
        (unanswerable("dress-code", document="rules.md"), NOT_FOUND),
    )

    markdown = render_markdown(report)

    fact_row = (
        "| fact | 1 | 0 | 100% (1/1) | 100% (1/1) | 100% (1/1) | 0% (0/1) | n/a |"
    )
    missing_row = (
        "| missing_related | 1 | 0 | 100% (1/1) | n/a | n/a | n/a | 100% (1/1) |"
    )
    assert fact_row in markdown
    assert missing_row in markdown
    assert "| handbook.md | 1 |" in markdown
    assert "| rules.md | 1 |" in markdown


async def test_rate_with_nothing_to_count_shows_as_not_applicable() -> None:
    report = await report_for((unanswerable("parking"), NOT_FOUND))

    markdown = render_markdown(report)

    assert "| Answer accuracy | n/a |" in markdown
    assert "| Not found accuracy | 100% (1/1) |" in markdown


@pytest.mark.parametrize(
    ("question", "script", "reasons"),
    [
        pytest.param(
            make_question("remote-days"),
            answered("Employees can work from home.", 2, "3 days a week"),
            "missing fact: 3 days / three days",
            id="missing_fact",
        ),
        pytest.param(
            make_question("remote-days"),
            answered("3 days.", 3, "The office opens at 8:00."),
            "evidence handbook.md line 2 not cited",
            id="evidence_line_not_cited",
        ),
        pytest.param(
            make_question("remote-days", evidence=[[2, 3]]),
            answered("3 days.", 1, "# Handbook"),
            "evidence handbook.md lines 2–3 not cited",
            id="evidence_lines_not_cited",
        ),
        pytest.param(
            make_question(
                "remote-days-and-dress",
                category="cross_document",
                evidence=[[2, 2], ["rules.md", 1, 1]],
            ),
            RIGHT,
            "evidence rules.md line 1 not cited",
            id="evidence_in_another_file_not_cited",
        ),
        pytest.param(
            make_question("remote-days"),
            answered("3 days, or 5 days in summer.", 2, "3 days a week"),
            "said a forbidden phrase: 5 days",
            id="forbidden_phrase",
        ),
        pytest.param(
            make_question("remote-days"),
            answered("Two days.", 3, "The office opens at 8:00."),
            "missing fact: 3 days / three days; evidence handbook.md line 2 not cited",
            id="several_reasons",
        ),
        pytest.param(
            make_question("remote-days"), NOT_FOUND, "said not found", id="not_found"
        ),
        pytest.param(
            make_question("remote-days"),
            answered("3 days.", 2, "5 days a week"),
            "citations rejected by the verifier",
            id="rejected_by_the_verifier",
        ),
        pytest.param(
            unanswerable("parking"),
            answered("At 8:00.", 3, "The office opens at 8:00."),
            "answered a question the documents can't answer",
            id="answered_the_unanswerable",
        ),
        pytest.param(
            make_question("remote-days"),
            GeminiUnavailableError("Busy."),
            "Gemini error: GeminiUnavailableError",
            id="gemini_error",
        ),
    ],
)
async def test_markdown_says_why_each_wrong_run_was_wrong(
    question: Question, script: Script, reasons: str
) -> None:
    report = await report_for((question, script), (make_question("right"), RIGHT))

    markdown = render_markdown(report)

    assert markdown.endswith(
        f"## Runs that weren't correct\n\n- `{question.id}` #1: {reasons}\n"
    )


async def test_markdown_says_so_when_every_run_was_correct() -> None:
    report = await report_for((make_question("remote-days"), RIGHT))

    assert render_markdown(report).endswith("## Runs that weren't correct\n\nNone.\n")


async def test_markdown_leaves_out_the_answers() -> None:
    secret = "Employees may also work from a beach in Brno, 3 days a week."
    report = await report_for(
        (make_question("remote-days"), answered(secret, 2, "3 days a week"))
    )

    assert secret in json.dumps(report)
    assert "beach" not in render_markdown(report)
