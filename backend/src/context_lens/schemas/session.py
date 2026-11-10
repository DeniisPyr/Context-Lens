from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Not stripped, unlike the other requests: a space can be part of a password.
    password: str = Field(min_length=1, max_length=1000)


class SessionResponse(BaseModel):
    login_required: bool
    # True whenever no login is required.
    logged_in: bool
