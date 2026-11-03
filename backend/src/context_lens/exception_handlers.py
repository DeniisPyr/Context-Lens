import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from context_lens.clients.gemini import GeminiError, GeminiUnavailableError
from context_lens.services.documents import (
    DocumentNotFoundError,
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentError,
)

logger = logging.getLogger(__name__)

DOCUMENT_ERROR_STATUS_CODES = {
    DocumentNotFoundError: 404,
    UnsupportedDocumentError: 415,
    DocumentTooLargeError: 413,
    EmptyDocumentError: 422,
}


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _handle_gemini_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # exc_info=exc rather than logger.exception(): a handler is not an except block.
    logger.error("Gemini is unavailable.", exc_info=exc)
    return _error_response(503, "Gemini is unavailable right now. Please try again.")


async def _handle_gemini_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Gemini could not answer.", exc_info=exc)
    return _error_response(502, "Gemini could not answer this question.")


async def _handle_document_error(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(DOCUMENT_ERROR_STATUS_CODES[type(exc)], str(exc))


def register_exception_handlers(app: FastAPI) -> None:
    # The most specific handler wins, so GeminiUnavailableError gets its own 503.
    app.add_exception_handler(GeminiUnavailableError, _handle_gemini_unavailable)
    app.add_exception_handler(GeminiError, _handle_gemini_error)
    for error_type in DOCUMENT_ERROR_STATUS_CODES:
        app.add_exception_handler(error_type, _handle_document_error)
