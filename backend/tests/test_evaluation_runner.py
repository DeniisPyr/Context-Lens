import asyncio

import pytest
from pydantic import BaseModel

from context_lens.clients.gemini import GeminiError, GeminiUnavailableError, TokenUsage
from context_lens.evaluation.cases import Question, QuestionSet
from context_lens.evaluation.runner import RecordingGemini, run_questions
from context_lens.evaluation.scoring import RunRecord, RunScore
from context_lens.services.answering import (
    NOT_FOUND_MESSAGE,
    SYSTEM_INSTRUCTION,
    Citation,
    ModelAnswer,
    build_prompt,
)
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
USAGE = TokenUsage(input_tokens=120, output_tokens=30, thought_tokens=45)


def make_question(question_id: str, **changes: object) -> Question:
    fields = {
        "id": question_id,
        "document": "handbook.md",
        "category": "fact",
        "question": f"Question {question_id}?",
        "facts": [["3 days"]],
        "evidence": [[2, 2]],
    }
    return Question.model_validate(fields | changes)


def make_set(*questions: Question) -> QuestionSet:
    return QuestionSet(list(questions), {"handbook.md": HANDBOOK}, "sha256:test")


def remote_days_answer(quote: str = "work from home 3 days a week") -> ModelAnswer:
    return ModelAnswer(
        status="answered",
        answer="Employees can work from home 3 days a week.",
        citations=[Citation(start_line=2, end_line=2, quote=quote)],
    )


class ScriptedGemini:
    def __init__(self, delay_seconds: dict[str, float] | None = None) -> None:
        # A question without a script gets remote_days_answer(), which passes the
        # verifier.
        self.scripts: dict[str, ModelAnswer | Exception] = {}
        self.delay_seconds = delay_seconds or {}
        self.calls: list[tuple[str, str, type[BaseModel]]] = []
        self.in_flight = 0
        self.most_in_flight = 0

    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]:
        self.calls.append((prompt, system_instruction, response_model))
        question = prompt.rpartition("Question: ")[2]
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay_seconds.get(question, 0))
        finally:
            self.in_flight -= 1
        script = self.scripts.get(question, remote_days_answer())
        if isinstance(script, Exception):
            raise script
        return response_model.model_validate(script.model_dump()), USAGE


async def test_run_records_the_answer_its_score_and_token_usage() -> None:
    question = make_question("remote-days")

    [record] = await run_questions(make_set(question), ScriptedGemini())

    assert record == RunRecord(
        question_id="remote-days",
        repeat=1,
        category="fact",
        document="handbook.md",
        question="Question remote-days?",
        facts=[["3 days"]],
        evidence=[(2, 2)],
        status="answered",
        answer="Employees can work from home 3 days a week.",
        citations=remote_days_answer().citations,
        raw_status="answered",
        raw_citations=None,
        seconds=record.seconds,
        input_tokens=120,
        output_tokens=30,
        thought_tokens=45,
        error=None,
        score=RunScore(
            correct=True,
            facts_found=[True],
            evidence_cited=[True],
            extra_citations=0,
            forbidden_found=[],
            rejected_by_verifier=False,
        ),
    )
    assert 0 <= record.seconds < 5


async def test_gemini_gets_the_prompt_the_app_sends() -> None:
    question = make_question("remote-days")
    gemini = ScriptedGemini()

    await run_questions(make_set(question), gemini)

    assert gemini.calls == [
        (build_prompt(question.question, HANDBOOK), SYSTEM_INSTRUCTION, ModelAnswer)
    ]


async def test_citation_the_verifier_rejects_gives_not_found() -> None:
    question = make_question("remote-days")
    gemini = ScriptedGemini()
    made_up = remote_days_answer(quote="work from home 5 days a week")
    gemini.scripts[question.question] = made_up

    [record] = await run_questions(make_set(question), gemini)

    assert record.status == "not_found"
    assert record.answer == NOT_FOUND_MESSAGE
    assert record.citations == []
    assert record.raw_status == "answered"
    assert record.raw_citations == made_up.citations
    assert record.score is not None
    assert record.score.rejected_by_verifier
    assert not record.score.correct


async def test_not_found_from_gemini_is_not_a_rejection() -> None:
    question = make_question(
        "parking", category="missing_related", facts=[], evidence=[]
    )
    gemini = ScriptedGemini()
    gemini.scripts[question.question] = ModelAnswer(
        status="not_found", answer="No idea.", citations=[]
    )

    [record] = await run_questions(make_set(question), gemini)

    assert record.status == "not_found"
    assert record.raw_status == "not_found"
    assert record.raw_citations is None
    assert record.score is not None
    assert record.score.correct
    assert not record.score.rejected_by_verifier


@pytest.mark.parametrize(
    ("error", "name"),
    [
        pytest.param(GeminiError("Gemini rejected it."), "GeminiError", id="rejected"),
        pytest.param(
            GeminiUnavailableError("Busy."), "GeminiUnavailableError", id="unavailable"
        ),
    ],
)
async def test_gemini_error_is_recorded_and_the_other_runs_go_on(
    error: GeminiError, name: str
) -> None:
    failing, working = make_question("failing"), make_question("working")
    gemini = ScriptedGemini()
    gemini.scripts[failing.question] = error

    records = await run_questions(make_set(failing, working), gemini)

    assert records[0].error == name
    assert records[0].status is None
    assert records[0].answer is None
    assert records[0].score is None
    assert (records[0].input_tokens, records[0].output_tokens) == (0, 0)
    assert records[1].error is None
    assert records[1].score is not None
    assert records[1].score.correct


async def test_other_exceptions_are_bugs_and_propagate() -> None:
    question = make_question("remote-days")
    gemini = ScriptedGemini()
    gemini.scripts[question.question] = RuntimeError("bug")

    with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match="bug")):
        await run_questions(make_set(question), gemini)


async def test_records_keep_their_order_whatever_order_runs_end_in() -> None:
    questions = [make_question(f"q{number}") for number in (1, 2, 3)]
    # The first question takes longest, so the runs end in reverse order.
    gemini = ScriptedGemini({"Question q1?": 0.06, "Question q2?": 0.03})
    progress: list[tuple[str, int, int, int]] = []

    def on_result(record: RunRecord, done: int, total: int) -> None:
        progress.append((record.question_id, record.repeat, done, total))

    records = await run_questions(
        make_set(*questions), gemini, repeats=2, concurrency=6, on_result=on_result
    )

    assert [(record.question_id, record.repeat) for record in records] == [
        ("q1", 1),
        ("q1", 2),
        ("q2", 1),
        ("q2", 2),
        ("q3", 1),
        ("q3", 2),
    ]
    assert [question_id for question_id, *_ in progress] == [
        "q3",
        "q3",
        "q2",
        "q2",
        "q1",
        "q1",
    ]
    assert [(done, total) for *_, done, total in progress] == [
        (number, 6) for number in range(1, 7)
    ]


@pytest.mark.parametrize("concurrency", [1, 2, 3])
async def test_concurrency_limits_the_calls_in_flight(concurrency: int) -> None:
    questions = [make_question(f"q{number}") for number in range(5)]
    gemini = ScriptedGemini({question.question: 0.01 for question in questions})

    await run_questions(make_set(*questions), gemini, concurrency=concurrency)

    assert gemini.most_in_flight == concurrency


async def test_repeats_ask_each_question_again() -> None:
    gemini = ScriptedGemini()

    records = await run_questions(
        make_set(make_question("remote-days")), gemini, repeats=3
    )

    assert [record.repeat for record in records] == [1, 2, 3]
    assert len(gemini.calls) == 3


async def test_recording_gemini_keeps_the_raw_answer_and_usage() -> None:
    recorder = RecordingGemini(ScriptedGemini())

    answer = await recorder.ask("Question remote-days?", "Be brief.", ModelAnswer)

    assert answer == remote_days_answer()
    assert recorder.raw_answer == answer
    assert recorder.usage == USAGE
