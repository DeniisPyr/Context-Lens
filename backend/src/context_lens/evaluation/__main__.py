import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from context_lens.clients.gemini import GeminiClient
from context_lens.evaluation.cases import (
    CATEGORIES,
    InvalidQuestionSetError,
    QuestionSet,
    load_question_set,
    select_questions,
)
from context_lens.evaluation.dataset import DocumentsById, IndexInfo, plan_index
from context_lens.evaluation.methods import (
    METHODS,
    DatasetSearch,
    Method,
    MethodName,
    WholeDocuments,
    prompt_characters_at_most,
)
from context_lens.evaluation.report import Report, build_report, render_markdown
from context_lens.evaluation.runner import GeminiWithUsage, build_index, run_questions
from context_lens.evaluation.scoring import RunRecord
from context_lens.services.indexing import IndexingError
from context_lens.settings import Settings

CHARACTERS_PER_TOKEN = 4
# Read from the class, so that a dry run needs no Settings() and so no Gemini key.
DEFAULT_CHUNKS_PER_QUESTION: int = Settings.model_fields["chunks_per_question"].default
SETTINGS_HELP = (
    "Set GEMINI_API_KEY in backend/.env and run this from backend/. If it's set, "
    "compare the other entries in .env with .env.example."
)


class ClosableGemini(GeminiWithUsage, Protocol):
    async def aclose(self) -> None: ...


type GeminiFactory = Callable[[Settings, str], ClosableGemini]


def connect_to_gemini(settings: Settings, model: str) -> GeminiClient:
    return GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        model,
        settings.gemini_embedding_model,
        settings.gemini_timeout_seconds,
    )


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {value}")
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m context_lens.evaluation",
        description=(
            "Asks Gemini every question in a question set, the way the app does, and "
            "reports how many answers and citations were right."
        ),
    )
    parser.add_argument(
        "--method",
        choices=METHODS,
        default="rag",
        help=(
            "rag answers from the chunks a search of all the documents finds, as the "
            "app does; whole_document sends each question's documents whole "
            "(default: rag)"
        ),
    )
    parser.add_argument(
        "--chunks",
        type=_positive_int,
        metavar="N",
        help=(
            "for rag, how many chunks each question gets "
            f"(default: {DEFAULT_CHUNKS_PER_QUESTION}, as in the app)"
        ),
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=Path("evals"),
        metavar="PATH",
        help="folder with questions.toml and documents/ (default: evals)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        help="write the JSON report here and the markdown next to it, as .md",
    )
    parser.add_argument(
        "--repeats",
        type=_positive_int,
        default=1,
        metavar="N",
        help="how many times to ask each question (default: 1)",
    )
    parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        metavar="N",
        help="how many questions to ask at once (default: 1)",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="ID",
        help="ask only the question with this id; repeat it to ask several",
    )
    parser.add_argument(
        "--model", metavar="NAME", help="the Gemini model, instead of GEMINI_MODEL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check the question set and estimate the prompts, without calling Gemini",
    )
    args = parser.parse_args(argv)
    if args.output is not None and args.output.suffix == ".md":
        # The markdown report goes to the same name with .md, over the JSON one.
        parser.error("--output is the JSON report, so it can't end in .md")
    if args.method != "rag" and args.chunks is not None:
        parser.error("--chunks is only for --method rag")
    if args.method == "rag" and args.chunks is None:
        args.chunks = DEFAULT_CHUNKS_PER_QUESTION
    return args


def _prompt_size(characters: int, bound: str = "") -> list[str]:
    tokens = round(characters / CHARACTERS_PER_TOKEN)
    return [
        f"Prompt characters over all runs{bound}: {characters:,}",
        f"Prompt tokens at {CHARACTERS_PER_TOKEN} characters a token{bound}: {tokens:,}",
    ]


def _rag_plan(question_set: QuestionSet, repeats: int, chunks: int | None) -> list[str]:
    plan = plan_index(question_set.documents.values())
    characters = repeats * sum(
        prompt_characters_at_most(question, plan.chunks, chunks)
        for question in question_set.questions
    )
    return [
        f"Chunks to embed: {len(plan.chunks)}",
        f"Characters to embed: {plan.characters_to_embed:,}",
        *_prompt_size(characters, ", at most"),
    ]


def _whole_document_plan(question_set: QuestionSet, repeats: int) -> list[str]:
    method = WholeDocuments(question_set.documents)
    characters = repeats * sum(
        method.prompt_characters(question) for question in question_set.questions
    )
    return _prompt_size(characters)


def describe_plan(
    question_set: QuestionSet, repeats: int, method: MethodName, chunks: int | None
) -> str:
    # chunks is None for whole_document, which doesn't search.
    if method == "whole_document":
        heading = f"Method: {method}"
        size = _whole_document_plan(question_set, repeats)
    else:
        heading = f"Method: {method}, {chunks} chunks a question"
        size = _rag_plan(question_set, repeats, chunks)
    questions = question_set.questions
    counts = Counter(question.category for question in questions)
    count = len(questions)
    lines = [
        heading,
        f"Questions: {count}",
        *(f"  {category}: {counts[category]}" for category in CATEGORIES),
        f"Documents: {len(question_set.documents)}",
        f"Runs: {count * repeats} (questions × repeats: {count} × {repeats})",
        *size,
    ]
    return "\n".join(lines)


def _print_progress(record: RunRecord, done: int, total: int) -> None:
    if record.score is None:
        outcome = f"Gemini error: {record.error}"
    else:
        outcome = "correct" if record.score.correct else "wrong"
    print(
        f"[{done}/{total}] {record.question_id} #{record.repeat}: {outcome} "
        f"({record.seconds:.1f} s)",
        file=sys.stderr,
    )


async def _prepare(
    args: argparse.Namespace, question_set: QuestionSet, gemini: ClosableGemini
) -> tuple[Method, IndexInfo | None]:
    if args.method == "whole_document":
        return WholeDocuments(question_set.documents), None
    # Once, before any question, as the app indexes a document once on upload.
    index, info = await build_index(question_set, gemini)
    documents = DocumentsById(question_set.documents.values())
    return DatasetSearch(index, documents, args.chunks), info


async def _evaluate(
    args: argparse.Namespace,
    question_set: QuestionSet,
    gemini: ClosableGemini,
    model: str,
) -> Report:
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    method, index = await _prepare(args, question_set, gemini)
    records = await run_questions(
        question_set, method, gemini, args.repeats, args.concurrency, _print_progress
    )
    return build_report(
        records,
        question_set,
        method=method.name,
        model=model,
        chunks_per_question=args.chunks,
        index=index,
        started_at=started_at,
        duration_seconds=time.perf_counter() - started,
        repeats=args.repeats,
        concurrency=args.concurrency,
    )


def _write(report: Report, markdown: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report_json = json.dumps(report, indent=2, ensure_ascii=False)
    path.write_text(report_json + "\n", encoding="utf-8")
    path.with_suffix(".md").write_text(markdown, encoding="utf-8")


async def _main(args: argparse.Namespace, connect: GeminiFactory) -> int:
    try:
        question_set = load_question_set(args.questions)
        if args.only:
            question_set = select_questions(question_set, args.only)
    except InvalidQuestionSetError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.dry_run:
        print(describe_plan(question_set, args.repeats, args.method, args.chunks))
        return 0

    try:
        settings = Settings()
    except ValidationError as exc:
        # Only the names: the error's input values can hold the database password.
        names = sorted(
            {str(detail["loc"][0]) for detail in exc.errors() if detail["loc"]}
        )
        print(f"Invalid settings: {', '.join(names)}. {SETTINGS_HELP}", file=sys.stderr)
        return 2
    model = args.model or settings.gemini_model
    # Kept in a variable until it's closed: the SDK fails with "client has been
    # closed" once the client is garbage collected.
    gemini = connect(settings, model)
    try:
        report = await _evaluate(args, question_set, gemini, model)
    except IndexingError as exc:
        print(
            f"Couldn't index the documents, so no question was asked: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        await gemini.aclose()

    markdown = render_markdown(report)
    if args.output is not None:
        _write(report, markdown, args.output)
        print(
            f"Wrote {args.output} and {args.output.with_suffix('.md')}.",
            file=sys.stderr,
        )
    print(markdown, end="")
    errors = report["summary"]["errors"]
    if errors:
        print(
            f"{errors} of {report['summary']['runs']} runs ended in a Gemini error, "
            "so the rates leave them out.",
            file=sys.stderr,
        )
    return 0


def main(
    argv: Sequence[str] | None = None, connect: GeminiFactory = connect_to_gemini
) -> int:
    return asyncio.run(_main(_parse_args(argv), connect))


if __name__ == "__main__":
    sys.exit(main())
