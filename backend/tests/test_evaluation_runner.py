import asyncio

import pytest
from conftest import word_embedding
from pydantic import BaseModel

from context_lens.clients.gemini import GeminiError, GeminiUnavailableError, TokenUsage
from context_lens.evaluation.cases import LineRange, Question, QuestionSet
from context_lens.evaluation.dataset import DocumentsById
from context_lens.evaluation.methods import (
    DatasetSearch,
    WholeDocuments,
    document_excerpt,
)
from context_lens.evaluation.runner import (
    OnResult,
    RecordingGemini,
    build_index,
    run_questions,
)
from context_lens.evaluation.scoring import RunRecord, RunScore
from context_lens.services.answering import (
    NOT_FOUND_MESSAGE,
    SYSTEM_INSTRUCTION,
    Citation,
    ModelAnswer,
    build_prompt,
)
from context_lens.services.documents import Document
from context_lens.services.embeddings import query_embedding_text
from context_lens.services.indexing import IndexingUnavailableError

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
RULES = Document(id="rules.md", filename="rules.md", text="# Rules\nDress well.\n")
POLICY = Document(id="policy.md", filename="policy.md", text="Lock your screen.\n")
# Two paragraphs too long for one chunk together, so each is a chunk of its own: lines
# 1 to 12 and 14 to 25.
LEAVE = Document(
    id="leave.md",
    filename="leave.md",
    text=(
        "".join(
            f"Annual leave rule {n}: book it in the portal first.\n" for n in range(12)
        )
        + "\n"
        + "".join(
            f"Sick leave rule {n}: tell your manager by nine.\n" for n in range(12)
        )
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
    documents = {document.id: document for document in (HANDBOOK, POLICY, RULES)}
    return QuestionSet(list(questions), documents, "sha256:test")


async def run_whole(
    question_set: QuestionSet,
    gemini: "ScriptedGemini",
    repeats: int = 1,
    concurrency: int = 1,
    on_result: OnResult | None = None,
) -> list[RunRecord]:
    method = WholeDocuments(question_set.documents)
    return await run_questions(
        question_set, method, gemini, repeats, concurrency, on_result
    )


async def run_rag(
    question_set: QuestionSet, gemini: "ScriptedGemini", chunks: int = 8
) -> list[RunRecord]:
    index, _ = await build_index(question_set, gemini)
    documents = DocumentsById(question_set.documents.values())
    method = DatasetSearch(index, documents, chunks)
    return await run_questions(question_set, method, gemini)


def remote_days_answer(quote: str = "work from home 3 days a week") -> ModelAnswer:
    return ModelAnswer(
        status="answered",
        answer="Employees can work from home 3 days a week.",
        citations=[Citation(file="handbook.md", start_line=2, end_line=2, quote=quote)],
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
        # The texts of each call to embed.
        self.embedded: list[list[str]] = []
        self.embed_error: Exception | None = None

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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded.append(texts)
        if self.embed_error is not None:
            raise self.embed_error
        return [word_embedding(text) for text in texts]


async def test_run_records_the_answer_its_score_and_token_usage() -> None:
    question = make_question("remote-days")

    [record] = await run_whole(make_set(question), ScriptedGemini())

    assert record == RunRecord(
        question_id="remote-days",
        repeat=1,
        category="fact",
        document="handbook.md",
        question="Question remote-days?",
        facts=[["3 days"]],
        evidence=[LineRange("handbook.md", 2, 2)],
        status="answered",
        answer="Employees can work from home 3 days a week.",
        citations=remote_days_answer().citations,
        raw_status="answered",
        raw_citations=None,
        excerpts=[LineRange("handbook.md", 1, 3)],
        evidence_shown=[True],
        seconds=record.seconds,
        input_tokens=120,
        output_tokens=30,
        thought_tokens=45,
        embedded_characters=0,
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

    await run_whole(make_set(question), gemini)

    prompt = build_prompt(question.question, [document_excerpt(HANDBOOK)])
    assert gemini.calls == [(prompt, SYSTEM_INSTRUCTION, ModelAnswer)]


async def test_cross_document_question_gets_its_document_then_each_other_one() -> None:
    question = make_question(
        "remote-days-and-dress",
        category="cross_document",
        facts=[["3 days"], ["Dress well"]],
        evidence=[["rules.md", 2, 2], [2, 2], ["policy.md", 1, 1]],
    )
    gemini = ScriptedGemini()
    gemini.scripts[question.question] = ModelAnswer(
        status="answered",
        answer="Work from home 3 days a week. Dress well. Lock your screen.",
        citations=[
            Citation(file="handbook.md", start_line=2, end_line=2, quote="3 days"),
            Citation(file="rules.md", start_line=2, end_line=2, quote="Dress well."),
            Citation(file="policy.md", start_line=1, end_line=1, quote="Lock"),
        ],
    )

    [record] = await run_whole(make_set(question), gemini)

    excerpts = [document_excerpt(document) for document in (HANDBOOK, RULES, POLICY)]
    assert gemini.calls == [
        (build_prompt(question.question, excerpts), SYSTEM_INSTRUCTION, ModelAnswer)
    ]
    assert record.evidence == [
        LineRange("rules.md", 2, 2),
        LineRange("handbook.md", 2, 2),
        LineRange("policy.md", 1, 1),
    ]
    assert record.score is not None
    assert record.score.evidence_cited == [True, True, True]
    assert record.score.correct


async def test_citation_the_verifier_rejects_gives_not_found() -> None:
    question = make_question("remote-days")
    gemini = ScriptedGemini()
    made_up = remote_days_answer(quote="work from home 5 days a week")
    gemini.scripts[question.question] = made_up

    [record] = await run_whole(make_set(question), gemini)

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

    [record] = await run_whole(make_set(question), gemini)

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

    records = await run_whole(make_set(failing, working), gemini)

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
        await run_whole(make_set(question), gemini)


async def test_records_keep_their_order_whatever_order_runs_end_in() -> None:
    questions = [make_question(f"q{number}") for number in (1, 2, 3)]
    # The first question takes longest, so the runs end in reverse order.
    gemini = ScriptedGemini({"Question q1?": 0.06, "Question q2?": 0.03})
    progress: list[tuple[str, int, int, int]] = []

    def on_result(record: RunRecord, done: int, total: int) -> None:
        progress.append((record.question_id, record.repeat, done, total))

    records = await run_whole(
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

    await run_whole(make_set(*questions), gemini, concurrency=concurrency)

    assert gemini.most_in_flight == concurrency


async def test_repeats_ask_each_question_again() -> None:
    gemini = ScriptedGemini()

    records = await run_whole(make_set(make_question("remote-days")), gemini, repeats=3)

    assert [record.repeat for record in records] == [1, 2, 3]
    assert len(gemini.calls) == 3


async def test_recording_gemini_keeps_the_raw_answer_and_usage() -> None:
    recorder = RecordingGemini(ScriptedGemini())

    answer = await recorder.ask("Question remote-days?", "Be brief.", ModelAnswer)

    assert answer == remote_days_answer()
    assert recorder.raw_answer == answer
    assert recorder.usage == USAGE


def leave_set(question: Question) -> QuestionSet:
    return QuestionSet([question], {"leave.md": LEAVE}, "sha256:test")


async def test_index_is_built_from_every_document_and_counts_what_it_embeds() -> None:
    gemini = ScriptedGemini()

    index, info = await build_index(make_set(), gemini)

    embedded = [text for texts in gemini.embedded for text in texts]
    assert len(gemini.embedded) == 3
    assert len(index) == info["chunks"] == 3
    assert info["embedded_characters"] == sum(map(len, embedded))
    assert 0 <= info["seconds"] < 5


async def test_rag_run_records_what_the_search_showed_gemini() -> None:
    question = make_question(
        "remote-days", question="How many days a week can employees work from home?"
    )
    gemini = ScriptedGemini()

    [record] = await run_rag(make_set(question), gemini, chunks=1)

    # The handbook is a single chunk, so its excerpt is the whole document.
    prompt = build_prompt(question.question, [document_excerpt(HANDBOOK)])
    assert gemini.calls == [(prompt, SYSTEM_INSTRUCTION, ModelAnswer)]
    assert record.excerpts == [LineRange("handbook.md", 1, 3)]
    assert record.evidence_shown == [True]
    assert record.embedded_characters == len(query_embedding_text(question.question))
    assert record.score is not None
    assert record.score.correct


async def test_rag_run_whose_search_missed_the_evidence_says_it_wasnt_shown() -> None:
    # The question shares its words with the rules, so the one chunk found is theirs.
    question = make_question("remote-days", question="Which rules say how to dress?")
    gemini = ScriptedGemini()
    gemini.scripts[question.question] = ModelAnswer(
        status="not_found", answer="No.", citations=[]
    )

    [record] = await run_rag(make_set(question), gemini, chunks=1)

    assert record.excerpts == [LineRange("rules.md", 1, 2)]
    assert record.evidence_shown == [False]
    assert record.score is not None
    assert not record.score.correct


@pytest.mark.parametrize(
    ("chunks", "excerpts", "shown"),
    [
        pytest.param(1, [LineRange("leave.md", 14, 25)], False, id="one_chunk"),
        pytest.param(
            2,
            [LineRange("leave.md", 1, 12), LineRange("leave.md", 14, 25)],
            True,
            id="both_chunks",
        ),
    ],
)
async def test_evidence_across_two_chunks_is_shown_only_when_both_are_found(
    chunks: int, excerpts: list[LineRange], shown: bool
) -> None:
    question = make_question(
        "sick-leave",
        document="leave.md",
        question="When must I tell my manager about sick leave?",
        evidence=[[12, 14]],
    )
    gemini = ScriptedGemini()
    gemini.scripts[question.question] = ModelAnswer(
        status="not_found", answer="No.", citations=[]
    )

    [record] = await run_rag(leave_set(question), gemini, chunks=chunks)

    assert record.excerpts == excerpts
    assert record.evidence_shown == [shown]


async def test_whole_document_run_shows_all_the_evidence() -> None:
    question = make_question(
        "remote-days-and-dress",
        category="cross_document",
        facts=[["3 days"], ["Dress well"]],
        evidence=[[2, 3], ["rules.md", 1, 2]],
    )

    [record] = await run_whole(make_set(question), ScriptedGemini())

    assert record.excerpts == [
        LineRange("handbook.md", 1, 3),
        LineRange("rules.md", 1, 2),
    ]
    assert record.evidence_shown == [True, True]
    assert record.embedded_characters == 0


@pytest.mark.parametrize("failing", ["embed", "ask"])
async def test_gemini_error_in_a_rag_run_is_recorded(failing: str) -> None:
    question = make_question("remote-days")
    gemini = ScriptedGemini()
    index, _ = await build_index(make_set(question), gemini)
    if failing == "embed":
        gemini.embed_error = GeminiUnavailableError("Busy.")
    else:
        gemini.scripts[question.question] = GeminiUnavailableError("Busy.")
    method = DatasetSearch(index, DocumentsById([HANDBOOK, POLICY, RULES]), 8)

    [record] = await run_questions(make_set(question), method, gemini)

    assert record.error == "GeminiUnavailableError"
    assert record.status is None
    assert record.excerpts == []
    assert record.evidence_shown is None
    assert record.score is None


async def test_index_fails_as_indexing_when_gemini_cant_embed() -> None:
    gemini = ScriptedGemini()
    gemini.embed_error = GeminiUnavailableError("Busy.")

    with pytest.raises(IndexingUnavailableError):
        await build_index(make_set(), gemini)


async def test_recording_gemini_counts_the_characters_it_embeds() -> None:
    gemini = ScriptedGemini()
    recorder = RecordingGemini(gemini)

    embeddings = await recorder.embed(["one", "three"])
    await recorder.embed(["seven"])

    assert embeddings == [word_embedding("one"), word_embedding("three")]
    assert gemini.embedded == [["one", "three"], ["seven"]]
    assert recorder.embedded_characters == 13
