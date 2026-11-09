import hashlib
import hmac
import re

from pydantic import SecretStr

# How long a login lasts: a working day. After that the browser drops the cookie and the
# app stops accepting it, so a cookie left on a shared computer doesn't stay useful.
SESSION_SECONDS = 12 * 60 * 60

# The signing key is derived from the password with this label, so that the key is
# used for signing sessions and nothing else.
SIGNING_KEY_LABEL = b"context-lens session"

# The expiry in whole seconds, a dot and the signature in hex. Anything else is not a
# session, and is turned away before it reaches the checks that could raise on it.
SESSION_PATTERN = re.compile(r"([0-9]{1,20})\.([0-9a-f]{64})")


class WrongPasswordError(Exception):
    """The password given to log in is not the access password."""

    def __init__(self) -> None:
        super().__init__("Wrong password.")


class NotLoggedInError(Exception):
    """A login is required, and the request has no valid session."""

    def __init__(self) -> None:
        super().__init__("Log in first.")


def _signing_key(password: SecretStr) -> bytes:
    # Derived from the password rather than kept as a second secret, so that changing
    # the password ends every session and there is nothing else to manage.
    return hmac.digest(
        password.get_secret_value().encode(), SIGNING_KEY_LABEL, "sha256"
    )


def _signature(expiry: str, password: SecretStr) -> str:
    return hmac.new(_signing_key(password), expiry.encode(), hashlib.sha256).hexdigest()


def _is_access_password(attempt: str, password: SecretStr) -> bool:
    # The digests have the same length whatever the passwords are, and compare_digest
    # takes as long however much of them matches, so the time a wrong guess takes tells
    # nothing about the password or its length.
    return hmac.compare_digest(
        hashlib.sha256(attempt.encode()).digest(),
        hashlib.sha256(password.get_secret_value().encode()).digest(),
    )


def sign_session(password: SecretStr, now: float) -> str:
    # The session holds only its expiry and is checked by its signature, so the app
    # keeps no sessions of its own: they survive a restart and work in every worker.
    expiry = str(int(now) + SESSION_SECONDS)
    return f"{expiry}.{_signature(expiry, password)}"


def is_valid_session(session: str, password: SecretStr, now: float) -> bool:
    match = SESSION_PATTERN.fullmatch(session)
    if match is None:
        return False
    expiry, signature = match.groups()
    # compare_digest takes as long wherever the first difference is, so the time doesn't
    # help to forge a signature one character at a time.
    if not hmac.compare_digest(signature, _signature(expiry, password)):
        return False
    return now < int(expiry)


def start_session(attempt: str, password: SecretStr | None, now: float) -> str | None:
    # Without a password there is nothing to log in to, so there is no session either.
    if password is None:
        return None
    if not _is_access_password(attempt, password):
        raise WrongPasswordError
    return sign_session(password, now)


def is_logged_in(session: str | None, password: SecretStr | None, now: float) -> bool:
    if password is None:
        return True
    return session is not None and is_valid_session(session, password, now)


def require_login(session: str | None, password: SecretStr | None, now: float) -> None:
    if not is_logged_in(session, password, now):
        raise NotLoggedInError
