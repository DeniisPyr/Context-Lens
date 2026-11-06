import math
import statistics
from collections.abc import Callable
from typing import TypedDict

from pydantic import BaseModel

from context_lens.evaluation.cases import ANSWERABLE, Category, Question
from context_lens.evaluation.matching import contains_phrase
from context_lens.services.answering import AnswerStatus, Citation, ModelAnswer


class RunScore(BaseModel):
    correct: bool
    facts_found: list[bool]
    evidence_cited: list[bool]
    extra_citations: int
    forbidden_found: list[str]
    rejected_by_verifier: bool


class RunRecord(BaseModel):
    question_id: str
    repeat: int
    category: Category
    document: str
    # What was expected, so the report can say what's missing without the set.
    question: str
    facts: list[list[str]]
    evidence: list[tuple[int, int]]
    # After verification. A run that ended in a Gemini error has no answer or score.
    status: AnswerStatus | None
    answer: str | None
    citations: list[Citation]
    raw_status: AnswerStatus | None
    # Only when the verifier rejected them, to show what Gemini cited instead.
    raw_citations: list[Citation] | None
    seconds: float
    input_tokens: int
    output_tokens: int
    thought_tokens: int
    error: str | None
    score: RunScore | None


class Rate(TypedDict):
    rate: float | None
    count: int
    of: int


class Summary(TypedDict):
    questions: int
    runs: int
    errors: int
    correct: Rate
    answerable_runs: int
    answer_accuracy: Rate
    citation_accuracy: Rate
    false_not_found_rate: Rate
    unanswerable_runs: int
    not_found_accuracy: Rate
    rejected_by_verifier: Rate
    median_seconds: float | None
    p95_seconds: float | None
    max_seconds: float | None
    mean_input_tokens: float | None
    mean_output_tokens: float | None
    total_input_tokens: int
    total_output_tokens: int


def _overlaps(citation: Citation, start: int, end: int) -> bool:
    return citation.start_line <= end and start <= citation.end_line


def score_run(
    question: Question, final: ModelAnswer, raw: ModelAnswer | None
) -> RunScore:
    facts_found = [
        any(contains_phrase(final.answer, phrase) for phrase in fact)
        for fact in question.facts
    ]
    evidence_cited = [
        any(_overlaps(citation, start, end) for citation in final.citations)
        for start, end in question.evidence
    ]
    extra_citations = sum(
        not any(_overlaps(citation, start, end) for start, end in question.evidence)
        for citation in final.citations
    )
    forbidden_found = [
        phrase for phrase in question.forbidden if contains_phrase(final.answer, phrase)
    ]
    if question.answerable:
        correct = (
            final.status == "answered"
            and all(facts_found)
            and all(evidence_cited)
            and not forbidden_found
        )
    else:
        correct = final.status == "not_found"
    return RunScore(
        correct=correct,
        facts_found=facts_found,
        evidence_cited=evidence_cited,
        extra_citations=extra_citations,
        forbidden_found=forbidden_found,
        rejected_by_verifier=(
            raw is not None and raw.status == "answered" and final.status == "not_found"
        ),
    )


def _is_correct(record: RunRecord) -> bool:
    return record.score is not None and record.score.correct


def _answer_is_right(record: RunRecord) -> bool:
    score = record.score
    return (
        score is not None
        and record.status == "answered"
        and all(score.facts_found)
        and not score.forbidden_found
    )


def _evidence_is_cited(record: RunRecord) -> bool:
    return record.score is not None and all(record.score.evidence_cited)


def _said_not_found(record: RunRecord) -> bool:
    return record.status == "not_found"


def _was_rejected(record: RunRecord) -> bool:
    return record.score is not None and record.score.rejected_by_verifier


def _rate(records: list[RunRecord], counts: Callable[[RunRecord], bool]) -> Rate:
    count = sum(counts(record) for record in records)
    of = len(records)
    return Rate(rate=count / of if of else None, count=count, of=of)


def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None


def _nearest_rank(ordered: list[float], percent: int) -> float | None:
    if not ordered:
        return None
    return ordered[math.ceil(percent * len(ordered) / 100) - 1]


def _output_tokens(record: RunRecord) -> int:
    # Thinking is billed as output.
    return record.output_tokens + record.thought_tokens


def summarize(records: list[RunRecord]) -> Summary:
    # A run that ended in a Gemini error has no answer, so no rate or timing counts it.
    scored = [record for record in records if record.error is None]
    answerable = [record for record in scored if record.category in ANSWERABLE]
    unanswerable = [record for record in scored if record.category not in ANSWERABLE]
    seconds = sorted(record.seconds for record in scored)
    input_tokens = [record.input_tokens for record in scored]
    output_tokens = [_output_tokens(record) for record in scored]
    return Summary(
        questions=len({record.question_id for record in records}),
        runs=len(records),
        errors=len(records) - len(scored),
        correct=_rate(scored, _is_correct),
        answerable_runs=len(answerable),
        answer_accuracy=_rate(answerable, _answer_is_right),
        citation_accuracy=_rate(answerable, _evidence_is_cited),
        false_not_found_rate=_rate(answerable, _said_not_found),
        unanswerable_runs=len(unanswerable),
        not_found_accuracy=_rate(unanswerable, _said_not_found),
        rejected_by_verifier=_rate(scored, _was_rejected),
        median_seconds=statistics.median(seconds) if seconds else None,
        p95_seconds=_nearest_rank(seconds, 95),
        max_seconds=max(seconds, default=None),
        mean_input_tokens=_mean(input_tokens),
        mean_output_tokens=_mean(output_tokens),
        total_input_tokens=sum(input_tokens),
        total_output_tokens=sum(output_tokens),
    )
