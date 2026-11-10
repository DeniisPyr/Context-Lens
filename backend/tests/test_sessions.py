import hashlib
import hmac

import pytest
from pydantic import SecretStr

from context_lens.services.sessions import (
    SESSION_SECONDS,
    NotLoggedInError,
    WrongPasswordError,
    is_logged_in,
    is_valid_session,
    require_login,
    sign_session,
    start_session,
)

PASSWORD = SecretStr("correct horse battery staple")
# A fixed clock, so that a test decides exactly how old a session is.
NOW = 1_800_000_000.0
SESSION = sign_session(PASSWORD, NOW)
EXPIRY, SIGNATURE = SESSION.split(".")

JUNK = [
    pytest.param("", id="empty"),
    pytest.param(".", id="only_a_dot"),
    pytest.param("junk", id="junk"),
    pytest.param(f"{EXPIRY}.", id="no_signature"),
    pytest.param(f".{SIGNATURE}", id="no_expiry"),
    pytest.param(EXPIRY, id="only_the_expiry"),
    pytest.param(SIGNATURE, id="only_the_signature"),
    pytest.param(f"{SESSION}.", id="trailing_dot"),
    pytest.param(f"{SESSION}.{SIGNATURE}", id="two_signatures"),
    pytest.param(f" {SESSION}", id="leading_space"),
    pytest.param(f"{SESSION}\n", id="trailing_newline"),
    pytest.param(f"{EXPIRY}:{SIGNATURE}", id="other_separator"),
    pytest.param(f"{EXPIRY}.{SIGNATURE.upper()}", id="upper_case_signature"),
    pytest.param(f"{EXPIRY}.{SIGNATURE[:-1]}", id="short_signature"),
    pytest.param(f"{EXPIRY}.{SIGNATURE}0", id="long_signature"),
    pytest.param(f"{EXPIRY}.{SIGNATURE[:-1]}é", id="non_ascii_signature"),
    pytest.param(f"-{EXPIRY}.{SIGNATURE}", id="negative_expiry"),
    pytest.param(f"{EXPIRY}.5.{SIGNATURE}", id="fractional_expiry"),
    pytest.param(f"{'٩' * 10}.{SIGNATURE}", id="arabic_digits"),
    pytest.param(f"{'9' * 25}.{SIGNATURE}", id="huge_expiry"),
    pytest.param(f"{EXPIRY}\x00.{SIGNATURE}", id="nul"),
    pytest.param("é" * 100, id="non_ascii"),
    pytest.param("9" * 10_000, id="very_long"),
]


def with_one_character_changed(text: str, position: int) -> str:
    replacement = "1" if text[position] == "0" else "0"
    return text[:position] + replacement + text[position + 1 :]


def test_session_is_valid_until_it_expires() -> None:
    assert is_valid_session(SESSION, PASSWORD, NOW)
    assert is_valid_session(SESSION, PASSWORD, NOW + SESSION_SECONDS - 1)


def test_session_expires_after_twelve_hours() -> None:
    assert SESSION_SECONDS == 12 * 60 * 60
    assert not is_valid_session(SESSION, PASSWORD, NOW + SESSION_SECONDS)
    assert not is_valid_session(SESSION, PASSWORD, NOW + 100 * SESSION_SECONDS)


def test_session_holds_its_expiry_and_a_signature_but_not_the_password() -> None:
    assert EXPIRY == str(int(NOW) + SESSION_SECONDS)
    assert len(SIGNATURE) == 64
    assert PASSWORD.get_secret_value() not in SESSION


def signed_with(key: bytes) -> str:
    return hmac.new(key, EXPIRY.encode(), hashlib.sha256).hexdigest()


def test_signing_key_is_slow_to_derive_rather_than_a_plain_hmac() -> None:
    password = PASSWORD.get_secret_value().encode()
    hmac_key = hmac.digest(password, b"context-lens session", "sha256")
    # Written out, so that making the key cheaper to guess fails here.
    scrypt_key = hashlib.scrypt(
        password,
        salt=b"context-lens session",
        n=2**16,
        r=8,
        p=1,
        maxmem=2**27,
        dklen=32,
    )

    assert SIGNATURE != signed_with(hmac_key)
    assert SIGNATURE == signed_with(scrypt_key)


def test_signing_key_is_derived_once_for_each_password(
    scrypt_calls: list[None],
) -> None:
    # A password no other test uses, so that its key isn't derived yet. A new SecretStr
    # each time, as the app's settings would give after a restart.
    text = "a password only this test uses"

    for second in range(3):
        session = sign_session(SecretStr(text), NOW + second)
        assert is_valid_session(session, SecretStr(text), NOW)
        assert start_session(text, SecretStr(text), NOW) is not None

    assert len(scrypt_calls) == 1


def test_same_password_and_time_sign_the_same_session() -> None:
    # Nothing is kept between calls, so another worker, or the app after a restart,
    # accepts the session.
    assert sign_session(PASSWORD, NOW) == SESSION
    assert is_valid_session(sign_session(PASSWORD, NOW), PASSWORD, NOW)


@pytest.mark.parametrize(
    "old_password",
    [
        pytest.param("an old password", id="other"),
        pytest.param(PASSWORD.get_secret_value() + " ", id="trailing_space"),
        pytest.param(PASSWORD.get_secret_value().upper(), id="upper_case"),
        pytest.param("", id="empty"),
    ],
)
def test_session_signed_under_another_password_is_not_valid(old_password: str) -> None:
    session = sign_session(SecretStr(old_password), NOW)

    assert session.split(".")[0] == EXPIRY
    assert session != SESSION
    assert not is_valid_session(session, PASSWORD, NOW)


def test_later_expiry_with_the_old_signature_is_not_valid() -> None:
    later = str(int(EXPIRY) + SESSION_SECONDS)

    assert not is_valid_session(f"{later}.{SIGNATURE}", PASSWORD, NOW)
    assert not is_valid_session(f"{later}.{SIGNATURE}", PASSWORD, NOW + SESSION_SECONDS)


def test_signature_of_another_session_is_not_valid() -> None:
    other = sign_session(PASSWORD, NOW + 1)

    assert not is_valid_session(f"{EXPIRY}.{other.split('.')[1]}", PASSWORD, NOW)


@pytest.mark.parametrize("position", range(64))
def test_signature_with_one_character_changed_is_not_valid(position: int) -> None:
    changed = with_one_character_changed(SIGNATURE, position)

    assert not is_valid_session(f"{EXPIRY}.{changed}", PASSWORD, NOW)


@pytest.mark.parametrize("session", JUNK)
def test_junk_is_not_a_session(session: str) -> None:
    assert not is_valid_session(session, PASSWORD, NOW)
    assert not is_logged_in(session, PASSWORD, NOW)
    with pytest.raises(NotLoggedInError):
        require_login(session, PASSWORD, NOW)


def test_right_password_starts_a_session() -> None:
    session = start_session(PASSWORD.get_secret_value(), PASSWORD, NOW)

    assert session == SESSION
    assert is_valid_session(session, PASSWORD, NOW)


def test_password_with_any_characters_starts_a_session() -> None:
    password = SecretStr("Příliš žluťoučký kůň 🐎 \"'%s;--")

    session = start_session(password.get_secret_value(), password, NOW)

    assert session is not None
    assert is_valid_session(session, password, NOW)


@pytest.mark.parametrize(
    "attempt",
    [
        pytest.param("wrong", id="other"),
        pytest.param("", id="empty"),
        pytest.param(PASSWORD.get_secret_value().upper(), id="upper_case"),
        pytest.param(PASSWORD.get_secret_value()[:-1], id="prefix"),
        pytest.param(PASSWORD.get_secret_value() + "e", id="longer"),
        pytest.param(" " + PASSWORD.get_secret_value(), id="leading_space"),
        pytest.param(PASSWORD.get_secret_value() + "\n", id="trailing_newline"),
    ],
)
def test_wrong_password_starts_no_session(attempt: str) -> None:
    with pytest.raises(WrongPasswordError) as raised:
        start_session(attempt, PASSWORD, NOW)

    assert str(raised.value) == "Wrong password."
    assert raised.value.args == ("Wrong password.",)


def test_without_a_password_logging_in_starts_no_session() -> None:
    assert start_session("anything", None, NOW) is None


@pytest.mark.parametrize(
    "session",
    [
        pytest.param(None, id="no_session"),
        pytest.param("junk", id="junk"),
        pytest.param(SESSION, id="valid_session"),
    ],
)
def test_without_a_password_everyone_is_logged_in(session: str | None) -> None:
    assert is_logged_in(session, None, NOW)
    require_login(session, None, NOW)


def test_with_a_password_a_valid_session_is_logged_in() -> None:
    assert is_logged_in(SESSION, PASSWORD, NOW)
    require_login(SESSION, PASSWORD, NOW)


@pytest.mark.parametrize(
    ("session", "now"),
    [
        pytest.param(None, NOW, id="no_session"),
        pytest.param(SESSION, NOW + SESSION_SECONDS, id="expired"),
        pytest.param(sign_session(SecretStr("old"), NOW), NOW, id="old_password"),
    ],
)
def test_with_a_password_others_are_not_logged_in(
    session: str | None, now: float
) -> None:
    assert not is_logged_in(session, PASSWORD, now)
    with pytest.raises(NotLoggedInError) as raised:
        require_login(session, PASSWORD, now)

    assert str(raised.value) == "Log in first."
