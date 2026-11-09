import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from context_lens.evaluation.cases import CATEGORIES
from context_lens.evaluation.report import (
    NOT_APPLICABLE,
    Report,
    failure_detail,
    format_rate,
    markdown_table,
    plural,
    summary_rows,
)
from context_lens.evaluation.scoring import RunRecord

REPORT = TypeAdapter(Report)
RUNS = TypeAdapter(list[RunRecord])
# What each category is compared on: its name in the table and in a summary.
CATEGORY_MEASURES = [
    ("Correct", "correct"),
    ("Answer accuracy", "answer_accuracy"),
    ("Clarified", "clarified"),
    ("Needless clarification", "needless_clarification"),
]


class InvalidReportError(Exception):
    """A report can't be compared; the message names its file."""


@dataclass(frozen=True)
class Side:
    # What the comparison calls the report, such as its method.
    label: str
    path: Path
    report: Report
    records: list[RunRecord]


def _problem(path: Path, error: ValidationError, *within: str) -> InvalidReportError:
    # Only the first problem, so that a report in an older format takes one line.
    detail = error.errors()[0]
    where = ".".join(map(str, [*within, *detail["loc"]]))
    return InvalidReportError(
        f"{path} is not an evaluation report in the current format: "
        f"{where}: {detail['msg']}."
    )


def _load(path: Path) -> tuple[Report, list[RunRecord]]:
    try:
        data = json.loads(path.read_bytes())
    except OSError as exc:
        raise InvalidReportError(f"Can't read {path}: {exc.strerror}.") from None
    except ValueError as exc:
        raise InvalidReportError(f"{path} is not JSON: {exc}.") from None
    try:
        report = REPORT.validate_python(data)
    except ValidationError as exc:
        raise _problem(path, exc) from None
    try:
        records = RUNS.validate_python(report["runs"])
    except ValidationError as exc:
        raise _problem(path, exc, "runs") from None
    return report, records


def _sides(first: Path, second: Path) -> tuple[Side, Side]:
    (a, a_records), (b, b_records) = _load(first), _load(second)
    if a["question_set"]["fingerprint"] != b["question_set"]["fingerprint"]:
        raise InvalidReportError(
            f"{first} and {second} are of different question sets, so they can't be "
            "compared."
        )
    # By method when the methods differ, since that's usually what's compared.
    labels = (a["method"], b["method"]) if a["method"] != b["method"] else ("A", "B")
    return (
        Side(labels[0], first, a, a_records),
        Side(labels[1], second, b, b_records),
    )


def _chunks(report: Report) -> str:
    chunks = report["chunks_per_question"]
    return NOT_APPLICABLE if chunks is None else str(chunks)


def _header_rows(a: Side, b: Side) -> list[list[str]]:
    return [
        ["Report", str(a.path), str(b.path)],
        ["Method", a.report["method"], b.report["method"]],
        ["Model", a.report["model"], b.report["model"]],
        ["Repeats", str(a.report["repeats"]), str(b.report["repeats"])],
        ["Chunks per question", _chunks(a.report), _chunks(b.report)],
    ]


def _summary_rows(a: Side, b: Side) -> list[list[str]]:
    return [
        [measure, a_value, b_value]
        for (measure, a_value), (_, b_value) in zip(
            summary_rows(a.report["summary"]),
            summary_rows(b.report["summary"]),
            strict=True,
        )
    ]


def _category_rows(a: Side, b: Side) -> list[list[str]]:
    rows = []
    for category in CATEGORIES:
        summaries = [side.report["by_category"].get(category) for side in (a, b)]
        if summaries == [None, None]:
            continue
        cells = [
            NOT_APPLICABLE if summary is None else format_rate(summary[measure])
            for _, measure in CATEGORY_MEASURES
            for summary in summaries
        ]
        rows.append([category, *cells])
    return rows


def _correct_runs(side: Side, question_id: str) -> tuple[int, int]:
    runs = [record for record in side.records if record.question_id == question_id]
    correct = sum(record.score is not None and record.score.correct for record in runs)
    return correct, len(runs)


def _difference(a: Side, b: Side, question_id: str) -> list[str]:
    a_correct, a_runs = _correct_runs(a, question_id)
    b_correct, b_runs = _correct_runs(b, question_id)
    # As shares, so that reports with different repeats can be compared.
    if a_correct * b_runs == b_correct * a_runs:
        return []
    worse = a if a_correct * b_runs < b_correct * a_runs else b
    failures = [
        f"  - {worse.label} #{record.repeat}: {failure_detail(record)}"
        for record in worse.records
        if record.question_id == question_id
        and not (record.score is not None and record.score.correct)
    ]
    counts = f"{a.label} {a_correct}/{a_runs}, {b.label} {b_correct}/{b_runs}"
    return [f"- `{question_id}`: {counts}", *failures]


def _differences(a: Side, b: Side) -> list[str]:
    # Questions both reports asked, in the first one's order.
    in_b = {record.question_id for record in b.records}
    question_ids = dict.fromkeys(
        record.question_id for record in a.records if record.question_id in in_b
    )
    return [
        line for question_id in question_ids for line in _difference(a, b, question_id)
    ]


def render_comparison(a: Side, b: Side) -> str:
    question_set = a.report["question_set"]
    questions = plural(question_set["questions"], "question")
    documents = plural(question_set["documents"], "document")
    labels = [a.label, b.label]
    category_columns = [
        f"{measure}, {label}" for measure, _ in CATEGORY_MEASURES for label in labels
    ]
    lines = [
        f"# Answer quality compared: {a.label} and {b.label}",
        "",
        f"{questions} about {documents} (set {question_set['fingerprint']}).",
        "",
        *markdown_table(["", *labels], _header_rows(a, b)),
        "",
        "## Summary",
        "",
        *markdown_table(["Measure", *labels], _summary_rows(a, b)),
        "",
        "## By category",
        "",
        *markdown_table(["Category", *category_columns], _category_rows(a, b)),
        "",
        "## Questions with different results",
        "",
        *(_differences(a, b) or ["None."]),
    ]
    return "\n".join(lines) + "\n"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m context_lens.evaluation.compare",
        description=(
            "Compares two saved evaluation reports of the same question set, side by "
            "side, and lists the questions whose results differ."
        ),
    )
    parser.add_argument("first", type=Path, metavar="A.json", help="a JSON report")
    parser.add_argument("second", type=Path, metavar="B.json", help="another one")
    parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH.md",
        help="also write the comparison here, as markdown",
    )
    args = parser.parse_args(argv)
    if args.output is not None and args.output.suffix != ".md":
        # So that a slip can't write over a JSON report.
        parser.error("--output is the markdown comparison, so it must end in .md")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        a, b = _sides(args.first, args.second)
    except InvalidReportError as exc:
        print(exc, file=sys.stderr)
        return 2
    markdown = render_comparison(a, b)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.output}.", file=sys.stderr)
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
