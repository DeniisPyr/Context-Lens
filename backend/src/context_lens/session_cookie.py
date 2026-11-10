from fastapi import Response

from context_lens.services.sessions import SESSION_SECONDS

COOKIE_NAME = "context_lens_session"
# The browser sends the cookie only to the API, which is all that reads it.
COOKIE_PATH = "/api"


def set_session_cookie(response: Response, session: str, secure: bool) -> None:
    # HttpOnly keeps the cookie from the page's scripts, and SameSite=Strict keeps the
    # browser from sending it with a request that another site starts.
    response.set_cookie(
        COOKIE_NAME,
        session,
        max_age=SESSION_SECONDS,
        path=COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def expire_session_cookie(response: Response, secure: bool) -> None:
    # With the same path, which is part of what makes it the same cookie to a browser.
    response.delete_cookie(
        COOKIE_NAME, path=COOKIE_PATH, secure=secure, httponly=True, samesite="strict"
    )
