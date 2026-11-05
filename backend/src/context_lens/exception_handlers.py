import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

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
DATABASE_UNAVAILABLE_ERRORS = (OperationalError, InterfaceError, PoolTimeoutError)


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


async def _handle_database_unavailable(
    request: Request, exc: Exception
) -> JSONResponse:
    # One line and no traceback: in an outage every request ends up here, and a traceback
    # runs to 200 lines. The first line is only the reason, without any statement.
    reason = str(exc).partition("\n")[0]
    logger.error("The database is unavailable: %s", reason)
    return _error_response(
        503, "The database is unavailable right now. Please try again."
    )


async def _handle_database_not_ready(request: Request, exc: Exception) -> JSONResponse:
    # A missing table or column raises this, which is how unapplied migrations show up.
    logger.error("The database isn't ready.", exc_info=exc)
    return _error_response(
        503,
        "The database isn't ready. Apply its migrations with: "
        "uv run alembic upgrade head",
    )


def register_exception_handlers(app: FastAPI) -> None:
    # The most specific handler wins, so GeminiUnavailableError gets its own 503.
    app.add_exception_handler(GeminiUnavailableError, _handle_gemini_unavailable)
    app.add_exception_handler(GeminiError, _handle_gemini_error)
    for error_type in DOCUMENT_ERROR_STATUS_CODES:
        app.add_exception_handler(error_type, _handle_document_error)
    for error_type in DATABASE_UNAVAILABLE_ERRORS:
        app.add_exception_handler(error_type, _handle_database_unavailable)
    app.add_exception_handler(ProgrammingError, _handle_database_not_ready)
