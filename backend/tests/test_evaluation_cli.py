import json
from pathlib import Path

import pytest
from conftest import word_embedding
from pydantic import BaseModel

from context_lens.clients.gemini import GeminiUnavailableError, TokenUsage
from context_lens.evaluation.__main__ import connect_to_gemini, main
from context_lens.evaluation.methods import document_excerpt
from context_lens.services.answering import (
    SYSTEM_INSTRUCTION,
    Citation,
    Clarification,
    ModelAnswer,
    build_prompt,
)
from context_lens.services.documents import Document
from context_lens.settings import Settings

HANDBOOK = (
    "# Handbook\n"
    "Employees can work from home 3 days a week.\n"
    "The office opens at 8:00.\n"
)
QUESTIONS_TOML = """\
[[questions]]
id = "handbook-remote-days"
document = "handbook.md"
category = "fact"
question = "How many days a week can employees work from home?"
facts = [["3 days", "three days"]]
evidence = [[2, 2]]

[[questions]]
id = "handbook-parking"
document = "handbook.md"
category = "missing_related"
question = "Where can employees park?"
"""
REMOTE_DAYS = "How many days a week can employees work from home?"
PARKING = "Where can employees park?"
OFFICES = "# Offices\nPrague opens at 8:00.\nBrno opens at 9:00.\n"
CLARIFY_TOML = """
[[questions]]
id = "offices-opening-time"
document = "offices.md"
category = "clarify"
question = "When does the office open?"
reply = "I work in Brno."
facts = [["9:00"]]
evidence = [[3, 3]]
cases = [[2, 3]]
"""
OPENING_TIME = "When does the office open?"
# What a dry run allows for the second prompt of a clarify question: its reply, to a
# clarifying question of 4000 characters, the most the app takes back.
ALLOWANCE = Clarification(question="?" * 4000, reply="I work in Brno.")


class ScriptedGemini:
    def __init__(self) -> None:
        self.scripts: dict[str, ModelAnswer | Exception] = {
            REMOTE_DAYS: ModelAnswer(
                status="answered",
                answer="Employees can work from home 3 days a week.",
                citations=[
                    Citation(
                        file="handbook.md",
                        start_line=2,
                        end_line=2,
                        quote="3 days a week",
                    )
                ],
            ),
            PARKING: ModelAnswer(status="not_found", answer="No.", citations=[]),
        }
        self.closed = False
        self.asked: list[str] = []
        # The texts of each call to embed.
        self.embedded: list[list[str]] = []
        self.embed_error: Exception | None = None

    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]:
        question = prompt.rpartition("Question: ")[2]
        self.asked.append(question)
        script = self.scripts[question]
        if isinstance(script, Exception):
            raise script
        usage = TokenUsage(input_tokens=100, output_tokens=20, thought_tokens=5)
        return response_model.model_validate(script.model_dump()), usage

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded.append(texts)
        if self.embed_error is not None:
            raise self.embed_error
        return [word_embedding(text) for text in texts]

    async def aclose(self) -> None:
        self.closed = True


class Connections:
    def __init__(self) -> None:
        self.gemini = ScriptedGemini()
        self.models: list[str] = []

    def __call__(self, settings: Settings, model: str) -> ScriptedGemini:
        self.models.append(model)
        return self.gemini


@pytest.fixture
def evals(tmp_path: Path) -> Path:
    # conftest made tmp_path the working directory, so this is the default folder.
    folder = tmp_path / "evals"
    (folder / "documents").mkdir(parents=True)
    (folder / "questions.toml").write_text(QUESTIONS_TOML)
    (folder / "documents" / "handbook.md").write_text(HANDBOOK)
    return folder


@pytest.fixture
def connections() -> Connections:
    return Connections()


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def prompt_characters(
    question: str,
    documents: dict[str, str] | None = None,
    clarification: Clarification | None = None,
) -> int:
    documents = documents or {"handbook.md": HANDBOOK}
    excerpts = [
        document_excerpt(Document(id=name, filename=name, text=text))
        for name, text in documents.items()
    ]
    prompt = build_prompt(question, excerpts, clarification=clarification)
    return len(SYSTEM_INSTRUCTION) + len(prompt)


def add_clarify_question(evals: Path) -> None:
    (evals / "documents" / "offices.md").write_text(OFFICES)
    with (evals / "questions.toml").open("a") as questions:
        questions.write(CLARIFY_TOML)


@pytest.mark.usefixtures("evals")
def test_dry_run_of_rag_describes_the_index_and_runs_without_a_key_or_gemini(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # The handbook is one chunk, so the most a search can show is all of it.
    characters = 2 * (prompt_characters(REMOTE_DAYS) + prompt_characters(PARKING))
    embedded = len("title: handbook.md | text: " + HANDBOOK.removesuffix("\n"))

    exit_code = main(["--dry-run", "--repeats", "2"], connections)

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == [
        "Method: rag, 8 chunks a question",
        "Questions: 2",
        "  fact: 1",
        "  multi_fact: 0",
        "  cross_document: 0",
        "  injection: 0",
        "  missing_related: 1",
        "  missing_unrelated: 0",
        "  clarify: 0",
        "Documents: 1",
        "Runs: 4 (questions × repeats: 2 × 2)",
        "Prompts, at most: 4 (runs + a second for each clarify run's reply: 4 + 0)",
        "Chunks to embed: 1",
        f"Characters to embed: {embedded:,}",
        f"Prompt characters over all runs, at most: {characters:,}",
        f"Prompt tokens at 4 characters a token, at most: {round(characters / 4):,}",
    ]
    assert connections.models == []


def test_dry_run_of_rag_counts_what_indexing_embeds(
    evals: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    connections: Connections,
) -> None:
    (evals / "documents" / "leave.md").write_text(
        "".join(
            f"Annual leave rule {n}: book it in the portal first.\n" for n in range(12)
        )
        + "\n"
        + "".join(
            f"Sick leave rule {n}: tell your manager by nine.\n" for n in range(12)
        )
    )
    main(["--dry-run"], connections)
    planned = capsys.readouterr().out.splitlines()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    main(["--output", "report.json"], connections)

    index = json.loads(Path("report.json").read_text())["index"]
    assert f"Chunks to embed: {index['chunks']}" in planned
    assert f"Characters to embed: {index['embedded_characters']:,}" in planned
    assert index["chunks"] == 3


@pytest.mark.usefixtures("evals")
def test_dry_run_of_rag_with_fewer_chunks_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--dry-run", "--chunks", "3"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("Method: rag, 3 chunks a question\n")


@pytest.mark.usefixtures("evals")
def test_dry_run_of_whole_document_describes_the_runs_without_a_key_or_gemini(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    characters = 2 * (prompt_characters(REMOTE_DAYS) + prompt_characters(PARKING))

    exit_code = main(
        ["--dry-run", "--method", "whole_document", "--repeats", "2"], connections
    )

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == [
        "Method: whole_document",
        "Questions: 2",
        "  fact: 1",
        "  multi_fact: 0",
        "  cross_document: 0",
        "  injection: 0",
        "  missing_related: 1",
        "  missing_unrelated: 0",
        "  clarify: 0",
        "Documents: 1",
        "Runs: 4 (questions × repeats: 2 × 2)",
        "Prompts, at most: 4 (runs + a second for each clarify run's reply: 4 + 0)",
        f"Prompt characters over all runs: {characters:,}",
        f"Prompt tokens at 4 characters a token: {round(characters / 4):,}",
    ]
    assert connections.models == []


def test_dry_run_counts_a_clarify_question_as_two_prompts(
    evals: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_clarify_question(evals)
    offices = {"offices.md": OFFICES}
    characters = 2 * (
        prompt_characters(REMOTE_DAYS)
        + prompt_characters(PARKING)
        + prompt_characters(OPENING_TIME, offices)
        + prompt_characters(OPENING_TIME, offices, ALLOWANCE)
    )

    exit_code = main(["--dry-run", "--method", "whole_document", "--repeats", "2"])

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines()[-6:] == [
        "  clarify: 1",
        "Documents: 2",
        "Runs: 6 (questions × repeats: 3 × 2)",
        "Prompts, at most: 8 (runs + a second for each clarify run's reply: 6 + 2)",
        # A bound, since the second prompt has the allowance in it.
        f"Prompt characters over all runs, at most: {characters:,}",
        f"Prompt tokens at 4 characters a token, at most: {round(characters / 4):,}",
    ]


def test_dry_run_of_rag_bounds_a_clarify_questions_second_prompt_as_its_first(
    evals: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_clarify_question(evals)
    # Each document is one chunk, so the most a search can show is both.
    both = {"handbook.md": HANDBOOK, "offices.md": OFFICES}
    characters = (
        prompt_characters(REMOTE_DAYS, both)
        + prompt_characters(PARKING, both)
        + prompt_characters(OPENING_TIME, both)
        + prompt_characters(OPENING_TIME, both, ALLOWANCE)
    )

    exit_code = main(["--dry-run"])

    assert exit_code == 0
    output = capsys.readouterr().out.splitlines()
    assert (
        "Prompts, at most: 4 (runs + a second for each clarify run's reply: 3 + 1)"
        in output
    )
    assert f"Prompt characters over all runs, at most: {characters:,}" in output


def test_dry_run_reads_the_folder_it_is_given(
    evals: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    moved = evals.rename(tmp_path / "elsewhere")

    exit_code = main(["--dry-run", "--questions", str(moved)])

    assert exit_code == 0
    assert "Questions: 2" in capsys.readouterr().out


@pytest.mark.usefixtures("evals")
def test_only_narrows_the_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        ["--dry-run", "--method", "whole_document", "--only", "handbook-parking"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Questions: 1" in output
    assert f"Prompt characters over all runs: {prompt_characters(PARKING):,}" in output


@pytest.mark.usefixtures("evals", "api_key")
def test_unknown_only_id_is_an_error(
    capsys: pytest.CaptureFixture[str], connections: Connections
) -> None:
    exit_code = main(["--only", "handbook-parking", "--only", "nope"], connections)

    assert exit_code == 2
    output = capsys.readouterr()
    assert output.err == "No question has the id nope.\n"
    assert output.out == ""
    assert connections.models == []


def test_invalid_question_set_is_an_error(
    evals: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (evals / "documents" / "handbook.md").unlink()

    exit_code = main(["--dry-run"])

    assert exit_code == 2
    assert capsys.readouterr().err == (
        "Question handbook-remote-days: handbook.md is not in evals/documents.\n"
    )


def test_missing_question_set_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--dry-run"])

    assert exit_code == 2
    assert capsys.readouterr().err.startswith("Can't read evals/questions.toml")


@pytest.mark.usefixtures("evals", "api_key")
def test_run_writes_both_reports_and_prints_the_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], connections: Connections
) -> None:
    exit_code = main(
        ["--output", "results/baseline.json", "--model", "other-model"], connections
    )

    assert exit_code == 0
    report = json.loads((tmp_path / "results" / "baseline.json").read_text())
    markdown = (tmp_path / "results" / "baseline.md").read_text()
    assert report["method"] == "rag"
    assert report["model"] == "other-model"
    assert report["chunks_per_question"] == 8
    assert report["index"]["chunks"] == 1
    assert [run["question_id"] for run in report["runs"]] == [
        "handbook-remote-days",
        "handbook-parking",
    ]
    assert report["summary"]["correct"] == {"rate": 1.0, "count": 2, "of": 2}
    assert report["summary"]["total_output_tokens"] == 50
    assert markdown.startswith("# Answer quality: rag, other-model\n")
    output = capsys.readouterr()
    assert output.out == markdown
    *progress, wrote = output.err.splitlines()
    assert len(progress) == 2
    assert wrote == "Wrote results/baseline.json and results/baseline.md."
    assert connections.models == ["other-model"]
    assert connections.gemini.closed


@pytest.mark.usefixtures("evals", "api_key")
def test_run_without_output_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "env-model")

    exit_code = main([], connections)

    assert exit_code == 0
    assert [path.name for path in tmp_path.iterdir()] == ["evals"]
    assert capsys.readouterr().out.startswith("# Answer quality: rag, env-model\n")
    assert connections.models == ["env-model"]


@pytest.mark.usefixtures("evals", "api_key")
def test_whole_document_run_sends_each_question_its_document_without_search(
    tmp_path: Path, connections: Connections
) -> None:
    exit_code = main(["--method", "whole_document", "--output", "w.json"], connections)

    assert exit_code == 0
    report = json.loads((tmp_path / "w.json").read_text())
    assert report["method"] == "whole_document"
    assert report["chunks_per_question"] is None
    assert report["index"] is None
    assert report["summary"]["correct"] == {"rate": 1.0, "count": 2, "of": 2}
    assert connections.gemini.embedded == []


@pytest.mark.usefixtures("api_key")
def test_run_of_a_clarify_question_sends_its_reply_and_reports_it(
    evals: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    add_clarify_question(evals)
    which_office = "Which office do you work in?"
    clarification = Clarification(question=which_office, reply="I work in Brno.")
    after_reply = build_prompt(OPENING_TIME, [], clarification=clarification)
    connections.gemini.scripts |= {
        OPENING_TIME: ModelAnswer(
            status="needs_clarification",
            answer=which_office,
            citations=[
                Citation(file="offices.md", start_line=2, end_line=3, quote="opens at")
            ],
        ),
        after_reply.rpartition("Question: ")[2]: ModelAnswer(
            status="answered",
            answer="It opens at 9:00.",
            citations=[
                Citation(file="offices.md", start_line=3, end_line=3, quote="9:00")
            ],
        ),
    }

    exit_code = main(["--method", "whole_document", "--output", "w.json"], connections)

    assert exit_code == 0
    report = json.loads((tmp_path / "w.json").read_text())
    assert report["summary"]["correct"] == {"rate": 1.0, "count": 3, "of": 3}
    assert report["summary"]["clarified"] == {"rate": 1.0, "count": 1, "of": 1}
    clarify_run = report["runs"][2]
    assert (clarify_run["clarification"], clarify_run["reply"]) == (
        which_office,
        "I work in Brno.",
    )
    progress = capsys.readouterr().err
    assert "[3/3] offices-opening-time #1: correct" in progress
    # Progress says how a run went, never what was asked or said.
    assert "Brno" not in progress
    assert "office" not in progress.replace("offices-opening-time", "")


@pytest.mark.usefixtures("api_key")
def test_rag_indexes_the_documents_once_for_all_the_runs(
    evals: Path, tmp_path: Path, connections: Connections
) -> None:
    (evals / "documents" / "rules.md").write_text("# Rules\nDress well.\n")

    exit_code = main(
        ["--repeats", "2", "--chunks", "1", "--output", "r.json"], connections
    )

    assert exit_code == 0
    indexing = [
        texts for texts in connections.gemini.embedded if texts[0].startswith("title: ")
    ]
    questions = [
        texts for texts in connections.gemini.embedded if texts[0].startswith("task: ")
    ]
    assert len(indexing) == 2
    assert questions == [
        [f"task: search result | query: {question}"]
        for question in (REMOTE_DAYS, REMOTE_DAYS, PARKING, PARKING)
    ]
    assert indexing == connections.gemini.embedded[:2]
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["chunks_per_question"] == 1
    assert report["index"]["chunks"] == 2
    assert [run["excerpts"] for run in report["runs"]] == [[["handbook.md", 1, 3]]] * 4


@pytest.mark.usefixtures("evals", "api_key")
def test_failed_indexing_stops_before_any_question(
    capsys: pytest.CaptureFixture[str], connections: Connections
) -> None:
    connections.gemini.embed_error = GeminiUnavailableError("Busy.")

    exit_code = main([], connections)

    assert exit_code == 1
    output = capsys.readouterr()
    assert output.err == (
        "Couldn't index the documents, so no question was asked: Gemini is "
        "unavailable right now.\n"
    )
    assert output.out == ""
    assert connections.gemini.asked == []
    assert connections.gemini.closed


@pytest.mark.usefixtures("evals", "api_key")
def test_gemini_error_while_embedding_a_question_is_that_runs_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    gemini = connections.gemini
    real_embed = gemini.embed

    async def embed(texts: list[str]) -> list[list[float]]:
        if texts[0].startswith("task: ") and PARKING in texts[0]:
            raise GeminiUnavailableError("Busy.")
        return await real_embed(texts)

    monkeypatch.setattr(gemini, "embed", embed)

    exit_code = main([], connections)

    assert exit_code == 0
    progress = capsys.readouterr().err.splitlines()
    assert progress[0].startswith("[1/2] handbook-remote-days #1: correct")
    assert progress[1].startswith(
        "[2/2] handbook-parking #1: Gemini error: GeminiUnavailableError"
    )


@pytest.mark.usefixtures("evals", "api_key")
def test_progress_has_a_line_for_each_run(
    capsys: pytest.CaptureFixture[str], connections: Connections
) -> None:
    connections.gemini.scripts[PARKING] = connections.gemini.scripts[REMOTE_DAYS]

    main(["--repeats", "2"], connections)

    lines = capsys.readouterr().err.splitlines()
    assert [line.split(" (")[0] for line in lines] == [
        "[1/4] handbook-remote-days #1: correct",
        "[2/4] handbook-remote-days #2: correct",
        "[3/4] handbook-parking #1: wrong",
        "[4/4] handbook-parking #2: wrong",
    ]
    assert all(line.endswith(" s)") for line in lines)


@pytest.mark.usefixtures("evals", "api_key")
def test_runs_that_ended_in_an_error_are_counted(
    capsys: pytest.CaptureFixture[str], connections: Connections
) -> None:
    connections.gemini.scripts[PARKING] = GeminiUnavailableError("Busy.")

    exit_code = main([], connections)

    assert exit_code == 0
    errors = capsys.readouterr().err.splitlines()
    assert errors[1].startswith(
        "[2/2] handbook-parking #1: Gemini error: GeminiUnavailableError ("
    )
    assert errors[2] == (
        "1 of 2 runs ended in a Gemini error, so the rates leave them out."
    )


@pytest.mark.usefixtures("evals", "api_key")
def test_gemini_is_closed_when_a_run_fails_with_a_bug(
    connections: Connections,
) -> None:
    connections.gemini.scripts[PARKING] = RuntimeError("bug")

    with pytest.RaisesGroup(RuntimeError):
        main([], connections)

    assert connections.gemini.closed


@pytest.mark.usefixtures("evals")
def test_missing_key_is_an_error_that_shows_no_settings_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    exit_code = main([], connections)

    assert exit_code == 2
    output = capsys.readouterr()
    assert output.err.startswith(
        "Invalid settings: gemini_api_key. Set GEMINI_API_KEY in backend/.env"
    )
    # conftest's DATABASE_URL has this password.
    assert "hunter2" not in output.err + output.out
    assert connections.models == []


@pytest.mark.anyio
@pytest.mark.usefixtures("api_key")
async def test_gemini_gets_the_model_asked_for_and_the_rest_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "env-embedding-model")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "7.5")

    gemini = connect_to_gemini(Settings(), "other-model")
    await gemini.aclose()

    assert gemini._model == "other-model"
    assert gemini._embedding_model == "env-embedding-model"
    assert gemini._timeout_seconds == 7.5


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--repeats", "0"], id="no_repeats"),
        pytest.param(["--concurrency", "two"], id="concurrency_not_a_number"),
        pytest.param(["--output", "baseline.md"], id="output_ending_in_md"),
        pytest.param(["--unknown"], id="unknown_option"),
        pytest.param(["--method", "keywords"], id="unknown_method"),
        pytest.param(["--chunks", "0"], id="no_chunks"),
        pytest.param(["--chunks", "many"], id="chunks_not_a_number"),
    ],
)
def test_bad_options_are_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith(
        "usage: python -m context_lens.evaluation"
    )


def test_chunks_with_whole_documents_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--method", "whole_document", "--chunks", "3"])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.endswith(
        "error: --chunks is only for --method rag\n"
    )
