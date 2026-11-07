import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from context_lens.clients.gemini import GeminiUnavailableError, TokenUsage
from context_lens.evaluation.__main__ import connect_to_gemini, main
from context_lens.services.answering import (
    SYSTEM_INSTRUCTION,
    Citation,
    ModelAnswer,
    build_prompt,
    document_excerpt,
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

    async def ask_with_usage[T: BaseModel](
        self, prompt: str, system_instruction: str, response_model: type[T]
    ) -> tuple[T, TokenUsage]:
        script = self.scripts[prompt.rpartition("Question: ")[2]]
        if isinstance(script, Exception):
            raise script
        usage = TokenUsage(input_tokens=100, output_tokens=20, thought_tokens=5)
        return response_model.model_validate(script.model_dump()), usage

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


def prompt_characters(question: str) -> int:
    document = Document(id="handbook.md", filename="handbook.md", text=HANDBOOK)
    prompt = build_prompt(question, [document_excerpt(document)])
    return len(SYSTEM_INSTRUCTION) + len(prompt)


@pytest.mark.usefixtures("evals")
def test_dry_run_describes_the_runs_without_a_key_or_gemini(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    connections: Connections,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    characters = 2 * (prompt_characters(REMOTE_DAYS) + prompt_characters(PARKING))

    exit_code = main(["--dry-run", "--repeats", "2"], connections)

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines() == [
        "Questions: 2",
        "  fact: 1",
        "  multi_fact: 0",
        "  injection: 0",
        "  missing_related: 1",
        "  missing_unrelated: 0",
        "Documents: 1",
        "Runs: 4 (questions × repeats: 2 × 2)",
        f"Prompt characters over all runs: {characters:,}",
        f"Prompt tokens at 4 characters a token: {round(characters / 4):,}",
    ]
    assert connections.models == []


def test_dry_run_reads_the_folder_it_is_given(
    evals: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    moved = evals.rename(tmp_path / "elsewhere")

    exit_code = main(["--dry-run", "--questions", str(moved)])

    assert exit_code == 0
    assert "Questions: 2" in capsys.readouterr().out


@pytest.mark.usefixtures("evals")
def test_only_narrows_the_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--dry-run", "--only", "handbook-parking"])

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
    assert report["method"] == "whole_document"
    assert report["model"] == "other-model"
    assert [run["question_id"] for run in report["runs"]] == [
        "handbook-remote-days",
        "handbook-parking",
    ]
    assert report["summary"]["correct"] == {"rate": 1.0, "count": 2, "of": 2}
    assert report["summary"]["total_output_tokens"] == 50
    assert markdown.startswith("# Answer quality: whole_document, other-model\n")
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
    assert capsys.readouterr().out.startswith(
        "# Answer quality: whole_document, env-model\n"
    )
    assert connections.models == ["env-model"]


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
