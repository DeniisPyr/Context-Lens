import time

from fastapi import APIRouter, Response

from context_lens.dependencies import SessionCookieDep, SettingsDep
from context_lens.schemas.session import LoginRequest, SessionResponse
from context_lens.services.sessions import is_logged_in, start_session
from context_lens.session_cookie import expire_session_cookie, set_session_cookie

router = APIRouter(prefix="/session", tags=["session"])


@router.get("")
async def read_session(
    session: SessionCookieDep, settings: SettingsDep
) -> SessionResponse:
    return SessionResponse(
        login_required=settings.access_password is not None,
        logged_in=is_logged_in(session, settings.access_password, time.time()),
    )


@router.post("", status_code=204)
async def log_in(body: LoginRequest, response: Response, settings: SettingsDep) -> None:
    session = start_session(body.password, settings.access_password, time.time())
    if session is not None:
        set_session_cookie(response, session, settings.secure_cookies)


@router.delete("", status_code=204)
async def log_out(response: Response, settings: SettingsDep) -> None:
    expire_session_cookie(response, settings.secure_cookies)
