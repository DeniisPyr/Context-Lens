import asyncio
import time
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel

from context_lens.clients.gemini import GeminiError, TokenUsage
from context_lens.evaluation.cases import Question, QuestionSet
from context_lens.evaluation.scoring import RunRecord, score_run
from context_lens.services.answering import (
    SYSTEM_INSTRUCTION,
    ModelAnswer,
    answer_question,
    build_prompt,
)
from context_lens.services.documents import Document

type OnResult = Callable[[RunRecord, int, int], None]


class GeminiWithUsage(Protocol):
    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]: ...


class RecordingGemini:
    # answer_question returns only the verified answer, so this keeps what Gemini
    # said before verification, and what it cost.
    def __init__(self, gemini: GeminiWithUsage) -> None:
        self._gemini = gemini
        self.raw_answer: ModelAnswer | None = None
        self.usage = TokenUsage()

    async def ask(
        self,
        prompt: str,
        system_instruction: str,
        response_model: type[ModelAnswer],
    ) -> ModelAnswer:
        answer, self.usage = await self._gemini.ask_with_usage(
            prompt, system_instruction, response_model
        )
        self.raw_answer = answer
        return answer


def prompt_characters(question: Question, document: Document) -> int:
    # What answer_question sends for the question.
    return len(SYSTEM_INSTRUCTION) + len(build_prompt(question.question, document))


async def _run_once(
    question: Question, repeat: int, document: Document, gemini: GeminiWithUsage
) -> RunRecord:
    recorder = RecordingGemini(gemini)
    final: ModelAnswer | None = None
    error: str | None = None
    started = time.perf_counter()
    try:
        final = await answer_question(question.question, document, recorder)
    except GeminiError as exc:
        error = type(exc).__name__
    seconds = time.perf_counter() - started

    raw = recorder.raw_answer
    score = None if final is None else score_run(question, final, raw)
    rejected = score is not None and score.rejected_by_verifier
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
        raw_citations=raw.citations if raw is not None and rejected else None,
        seconds=round(seconds, 3),
        input_tokens=recorder.usage.input_tokens,
        output_tokens=recorder.usage.output_tokens,
        thought_tokens=recorder.usage.thought_tokens,
        error=error,
        score=score,
    )


async def run_questions(
    question_set: QuestionSet,
    gemini: GeminiWithUsage,
    repeats: int = 1,
    concurrency: int = 1,
    on_result: OnResult | None = None,
) -> list[RunRecord]:
    jobs = [
        (question, repeat)
        for question in question_set.questions
        for repeat in range(1, repeats + 1)
    ]
    semaphore = asyncio.Semaphore(concurrency)
    done = 0

    async def run(question: Question, repeat: int) -> RunRecord:
        nonlocal done
        document = question_set.documents[question.document]
        async with semaphore:
            record = await _run_once(question, repeat, document, gemini)
        done += 1
        if on_result is not None:
            on_result(record, done, len(jobs))
        return record

    # A task group, so that a bug in one run cancels the others instead of leaving
    # them calling Gemini.
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(run(question, repeat)) for question, repeat in jobs]
    return [task.result() for task in tasks]
