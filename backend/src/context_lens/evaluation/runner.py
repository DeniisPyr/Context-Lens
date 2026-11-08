import asyncio
import time
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel

from context_lens.clients.gemini import GeminiError, TokenUsage
from context_lens.evaluation.cases import LineRange, Question, QuestionSet
from context_lens.evaluation.dataset import ChunkIndex, IndexInfo, index_documents
from context_lens.evaluation.methods import Method
from context_lens.evaluation.scoring import RunRecord, evidence_shown, score_run
from context_lens.services.answering import Excerpt, ModelAnswer
from context_lens.services.search import DatasetAnswer

type OnResult = Callable[[RunRecord, int, int], None]


class GeminiWithUsage(Protocol):
    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class RecordingGemini:
    # A method returns only the verified answer, so this keeps what Gemini said before
    # verification, and what it cost.
    def __init__(self, gemini: GeminiWithUsage) -> None:
        self._gemini = gemini
        self.raw_answer: ModelAnswer | None = None
        self.usage = TokenUsage()
        self.embedded_characters = 0

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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = await self._gemini.embed(texts)
        self.embedded_characters += sum(map(len, texts))
        return embeddings


async def build_index(
    question_set: QuestionSet, gemini: GeminiWithUsage
) -> tuple[ChunkIndex, IndexInfo]:
    recorder = RecordingGemini(gemini)
    started = time.perf_counter()
    index = await index_documents(question_set.documents.values(), recorder)
    info = IndexInfo(
        chunks=len(index),
        embedded_characters=recorder.embedded_characters,
        seconds=round(time.perf_counter() - started, 3),
    )
    return index, info


def _line_range(excerpt: Excerpt) -> LineRange:
    # An excerpt's lines follow on from each other.
    return LineRange(excerpt.filename, min(excerpt.lines), max(excerpt.lines))


async def _run_once(
    question: Question,
    repeat: int,
    question_set: QuestionSet,
    method: Method,
    gemini: GeminiWithUsage,
) -> RunRecord:
    recorder = RecordingGemini(gemini)
    result: DatasetAnswer | None = None
    error: str | None = None
    started = time.perf_counter()
    try:
        result = await method.answer(question, recorder)
    except GeminiError as exc:
        error = type(exc).__name__
    seconds = time.perf_counter() - started

    final = None if result is None else result.answer
    excerpts = [] if result is None else result.excerpts
    shown = [_line_range(excerpt) for excerpt in excerpts]
    documents = question_set.documents
    shown_evidence = (
        None if result is None else evidence_shown(question.evidence, shown, documents)
    )
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
        excerpts=shown,
        evidence_shown=shown_evidence,
        seconds=round(seconds, 3),
        input_tokens=recorder.usage.input_tokens,
        output_tokens=recorder.usage.output_tokens,
        thought_tokens=recorder.usage.thought_tokens,
        embedded_characters=recorder.embedded_characters,
        error=error,
        score=score,
    )


async def run_questions(
    question_set: QuestionSet,
    method: Method,
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
        async with semaphore:
            record = await _run_once(question, repeat, question_set, method, gemini)
        done += 1
        if on_result is not None:
            on_result(record, done, len(jobs))
        return record

    # A task group, so that a bug in one run cancels the others instead of leaving
    # them calling Gemini.
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(run(question, repeat)) for question, repeat in jobs]
    return [task.result() for task in tasks]
