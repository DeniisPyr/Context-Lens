from collections.abc import Callable
from datetime import datetime
from typing import Any, TypedDict

from context_lens.evaluation.cases import ANSWERABLE, CATEGORIES, QuestionSet
from context_lens.evaluation.scoring import Rate, RunRecord, Summary, summarize

METHOD = "whole_document"
NOT_APPLICABLE = "n/a"
GROUP_COLUMNS = [
    "Runs",
    "Errors",
    "Correct",
    "Answer accuracy",
    "Citation accuracy",
    "False not found",
    "Not found accuracy",
    "Median seconds",
    "Mean input tokens",
]


class QuestionSetInfo(TypedDict):
    questions: int
    documents: int
    fingerprint: str


class Report(TypedDict):
    method: str
    model: str
    started_at: str
    duration_seconds: float
    repeats: int
    concurrency: int
    question_set: QuestionSetInfo
    summary: Summary
    by_category: dict[str, Summary]
    by_document: dict[str, Summary]
    runs: list[dict[str, Any]]


def _summaries_by(
    records: list[RunRecord], names: list[str], key: Callable[[RunRecord], str]
) -> dict[str, Summary]:
    return {
        name: summarize([record for record in records if key(record) == name])
        for name in names
    }


def build_report(
    records: list[RunRecord],
    question_set: QuestionSet,
    *,
    model: str,
    started_at: datetime,
    duration_seconds: float,
    repeats: int,
    concurrency: int,
) -> Report:
    categories = [
        category
        for category in CATEGORIES
        if any(record.category == category for record in records)
    ]
    documents = sorted({record.document for record in records})
    return Report(
        method=METHOD,
        model=model,
        started_at=started_at.isoformat(timespec="seconds"),
        duration_seconds=round(duration_seconds, 3),
        repeats=repeats,
        concurrency=concurrency,
        question_set=QuestionSetInfo(
            questions=len(question_set.questions),
            documents=len(question_set.documents),
            fingerprint=question_set.fingerprint,
        ),
        summary=summarize(records),
        by_category=_summaries_by(records, categories, lambda record: record.category),
        by_document=_summaries_by(records, documents, lambda record: record.document),
        runs=[record.model_dump(mode="json") for record in records],
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _rate(rate: Rate) -> str:
    if rate["rate"] is None:
        return NOT_APPLICABLE
    return f"{rate['rate']:.0%} ({rate['count']}/{rate['of']})"


def _seconds(value: float | None) -> str:
    return NOT_APPLICABLE if value is None else f"{value:.1f}"


def _tokens(value: float | None) -> str:
    return NOT_APPLICABLE if value is None else f"{value:.0f}"


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    return [_row(header), _row(["---"] * len(header)), *map(_row, rows)]


def _summary_rows(summary: Summary) -> list[list[str]]:
    return [
        ["Questions", str(summary["questions"])],
        ["Runs", str(summary["runs"])],
        ["Gemini errors", str(summary["errors"])],
        ["Correct", _rate(summary["correct"])],
        ["Answer accuracy", _rate(summary["answer_accuracy"])],
        ["Citation accuracy", _rate(summary["citation_accuracy"])],
        ["False not found", _rate(summary["false_not_found_rate"])],
        ["Not found accuracy", _rate(summary["not_found_accuracy"])],
        ["Rejected by the verifier", _rate(summary["rejected_by_verifier"])],
        ["Median seconds", _seconds(summary["median_seconds"])],
        ["p95 seconds", _seconds(summary["p95_seconds"])],
        ["Max seconds", _seconds(summary["max_seconds"])],
        ["Mean input tokens", _tokens(summary["mean_input_tokens"])],
        ["Mean output tokens, with thinking", _tokens(summary["mean_output_tokens"])],
        ["Total input tokens", str(summary["total_input_tokens"])],
        ["Total output tokens, with thinking", str(summary["total_output_tokens"])],
    ]


def _group_rows(summaries: dict[str, Summary]) -> list[list[str]]:
    return [
        [
            name,
            str(summary["runs"]),
            str(summary["errors"]),
            _rate(summary["correct"]),
            _rate(summary["answer_accuracy"]),
            _rate(summary["citation_accuracy"]),
            _rate(summary["false_not_found_rate"]),
            _rate(summary["not_found_accuracy"]),
            _seconds(summary["median_seconds"]),
            _tokens(summary["mean_input_tokens"]),
        ]
        for name, summary in summaries.items()
    ]


def _lines(start: int, end: int) -> str:
    return f"line {start}" if start == end else f"lines {start}–{end}"


def _reasons(record: RunRecord) -> list[str]:
    score = record.score
    if score is None:
        return [f"Gemini error: {record.error}"]
    if record.status == "not_found":
        if score.rejected_by_verifier:
            return ["citations rejected by the verifier"]
        return ["said not found"]
    reasons = []
    if record.category not in ANSWERABLE:
        reasons.append("answered a question the documents can't answer")
    reasons += [
        f"missing fact: {' / '.join(fact)}"
        for fact, found in zip(record.facts, score.facts_found, strict=True)
        if not found
    ]
    reasons += [
        f"evidence {_lines(start, end)} not cited"
        for (start, end), cited in zip(
            record.evidence, score.evidence_cited, strict=True
        )
        if not cited
    ]
    reasons += [
        f"said a forbidden phrase: {phrase}" for phrase in score.forbidden_found
    ]
    return reasons


def render_markdown(report: Report) -> str:
    question_set = report["question_set"]
    records = [RunRecord.model_validate(run) for run in report["runs"]]
    failures = [
        f"- `{record.question_id}` #{record.repeat}: {'; '.join(_reasons(record))}"
        for record in records
        if record.score is None or not record.score.correct
    ]
    questions = _plural(question_set["questions"], "question")
    documents = _plural(question_set["documents"], "document")
    about = ", ".join(
        [
            f"{questions} about {documents} (set {question_set['fingerprint']})",
            _plural(report["repeats"], "repeat"),
            f"concurrency {report['concurrency']}",
            f"started {report['started_at']}",
            f"took {report['duration_seconds']:.1f} s",
        ]
    )
    lines = [
        f"# Answer quality: {report['method']}, {report['model']}",
        "",
        f"{about}.",
        "",
        "## Summary",
        "",
        *_table(["Measure", "Value"], _summary_rows(report["summary"])),
        "",
        "## By category",
        "",
        *_table(["Category", *GROUP_COLUMNS], _group_rows(report["by_category"])),
        "",
        "## By document",
        "",
        *_table(["Document", *GROUP_COLUMNS], _group_rows(report["by_document"])),
        "",
        "## Runs that weren't correct",
        "",
        *(failures or ["None."]),
    ]
    return "\n".join(lines) + "\n"
