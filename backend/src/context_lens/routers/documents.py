from pathlib import PureWindowsPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from context_lens.dependencies import get_document_store
from context_lens.documents import Document, DocumentStore

MAX_UPLOAD_BYTES = 1_000_000
ALLOWED_EXTENSIONS = {".txt", ".md"}

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    id: str
    filename: str
    line_count: int


def _to_summary(document: Document) -> DocumentSummary:
    return DocumentSummary(
        id=document.id, filename=document.filename, line_count=len(document.lines)
    )


def _clean_filename(filename: str | None) -> str:
    # PureWindowsPath splits on both / and \, so it handles paths from any client.
    path = PureWindowsPath(filename or "")
    # Names like "/" or "C:\" have no suffix, so this rejects them too.
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Only .txt and .md files are accepted.")
    if "\x00" in path.name:
        raise HTTPException(415, "The filename must not contain NUL characters.")
    return path.name


def _decode_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "The file must be valid UTF-8 text.") from exc
    if "\x00" in text:
        raise HTTPException(415, "The file must not contain NUL characters.")
    return text


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile,
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> DocumentSummary:
    filename = _clean_filename(file.filename)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"The file must not be larger than {MAX_UPLOAD_BYTES:,} bytes."
        )
    text = _decode_text(data)
    if not text.strip():
        raise HTTPException(422, "The file must not be empty.")
    return _to_summary(store.add(filename, text))


@router.get("")
async def list_documents(
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> list[DocumentSummary]:
    return [_to_summary(document) for document in store.list_all()]
