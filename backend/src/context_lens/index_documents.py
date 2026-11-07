import argparse
import asyncio
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

from pydantic import ValidationError

from context_lens.clients.gemini import GeminiClient
from context_lens.db.document_store import DocumentStore
from context_lens.db.engine import create_database_engine
from context_lens.services.chunking import split_into_chunks
from context_lens.services.documents import DocumentNotFoundError
from context_lens.services.indexing import (
    AlreadyIndexedError,
    IndexingError,
    index_lines,
    texts_to_embed,
)
from context_lens.settings import DatabaseSettings, Settings

CHARACTERS_PER_TOKEN = 4
SETTINGS_HELP = (
    "Set GEMINI_API_KEY in backend/.env and run this from backend/. If it's set, "
    "compare the other entries in .env with .env.example."
)
DELETED = "skipped, the document was deleted meanwhile"

type GeminiFactory = Callable[[Settings], GeminiClient]


@dataclass(frozen=True)
class Outcome:
    document: str
    result: str
    gemini_failed: bool = False


def connect_to_gemini(settings: Settings) -> GeminiClient:
    return GeminiClient(
        settings.gemini_api_key.get_secret_value(),
        settings.gemini_model,
        settings.gemini_embedding_model,
        settings.gemini_timeout_seconds,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m context_lens.index_documents",
        description=(
            "Indexes the documents stored before uploads made chunks: splits each "
            "into chunks, embeds them with Gemini and stores them."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="count the documents and characters to embed, without calling Gemini",
    )
    return parser.parse_args(argv)


def _load_settings[T: DatabaseSettings](settings_class: type[T]) -> T | None:
    try:
        return settings_class()
    except ValidationError as exc:
        # Only the names: the error's input values can hold the database password.
        names = sorted(
            {str(detail["loc"][0]) for detail in exc.errors() if detail["loc"]}
        )
        print(f"Invalid settings: {', '.join(names)}. {SETTINGS_HELP}", file=sys.stderr)
        return None


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@asynccontextmanager
async def _document_store(settings: DatabaseSettings) -> AsyncIterator[DocumentStore]:
    engine = create_database_engine(settings)
    try:
        yield DocumentStore(engine)
    finally:
        await engine.dispose()


async def _describe_plan(store: DocumentStore, document_ids: list[str]) -> str:
    documents = chunks = characters = 0
    # One at a time, because each text can be up to a megabyte.
    for document_id in document_ids:
        document = await store.get(document_id)
        if document is None:
            continue
        texts = texts_to_embed(document.filename, split_into_chunks(document.lines))
        documents += 1
        chunks += len(texts)
        characters += sum(map(len, texts))
    tokens = round(characters / CHARACTERS_PER_TOKEN)
    return "\n".join(
        [
            f"Documents without chunks: {documents}",
            f"Chunks to embed: {chunks}",
            f"Characters to embed: {characters:,}",
            f"Tokens at {CHARACTERS_PER_TOKEN} characters a token: {tokens:,}",
        ]
    )


async def _index_one(
    store: DocumentStore, gemini: GeminiClient, document_id: str
) -> Outcome:
    document = await store.get(document_id)
    if document is None:
        return Outcome(document_id, DELETED)
    # repr, so that a filename with a line break in it still takes one line.
    name = f"{document.id} {document.filename!r}"
    try:
        chunks = await index_lines(gemini, document.filename, document.lines)
    except IndexingError as exc:
        return Outcome(name, f"Gemini error: {type(exc).__name__}", gemini_failed=True)
    try:
        await store.add_chunks(document.id, chunks)
    except DocumentNotFoundError:
        return Outcome(name, DELETED)
    except AlreadyIndexedError:
        return Outcome(name, "skipped, another run indexed it meanwhile")
    return Outcome(name, _plural(len(chunks), "chunk"))


async def _index_all(
    store: DocumentStore, gemini: GeminiClient, document_ids: list[str]
) -> int:
    failed = 0
    total = len(document_ids)
    # One document at a time, each stored in a transaction of its own, so a failure
    # loses only that document's work and no connection waits for Gemini.
    for done, document_id in enumerate(document_ids, start=1):
        outcome = await _index_one(store, gemini, document_id)
        print(f"[{done}/{total}] {outcome.document}: {outcome.result}", file=sys.stderr)
        failed += outcome.gemini_failed
    if failed:
        print(
            f"{failed} of {_plural(total, 'document')} weren't indexed because of "
            "Gemini errors. Run this again to retry them.",
            file=sys.stderr,
        )
    return failed


async def _dry_run(settings: DatabaseSettings) -> int:
    async with _document_store(settings) as store:
        print(await _describe_plan(store, await store.ids_without_chunks()))
    return 0


async def _index(settings: Settings, connect: GeminiFactory) -> int:
    async with _document_store(settings) as store:
        document_ids = await store.ids_without_chunks()
        if not document_ids:
            print("No documents need indexing.", file=sys.stderr)
            return 0
        # Kept in a variable until it's closed: the SDK fails with "client has been
        # closed" once the client is garbage collected.
        gemini = connect(settings)
        try:
            failed = await _index_all(store, gemini, document_ids)
        finally:
            await gemini.aclose()
    return 1 if failed else 0


def main(
    argv: Sequence[str] | None = None, connect: GeminiFactory = connect_to_gemini
) -> int:
    args = _parse_args(argv)
    if args.dry_run:
        # The database's settings only, so that a dry run needs no Gemini key.
        database_settings = _load_settings(DatabaseSettings)
        if database_settings is None:
            return 2
        return asyncio.run(_dry_run(database_settings))
    settings = _load_settings(Settings)
    if settings is None:
        return 2
    return asyncio.run(_index(settings, connect))


if __name__ == "__main__":
    sys.exit(main())
