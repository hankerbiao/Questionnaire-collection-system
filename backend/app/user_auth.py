import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.secret_policy import configured_secret

USER_SESSION_COOKIE = "dml_user_session"
LOGIN_STATE_COOKIE = "dml_sso_state"
JWT_ALGORITHM = "HS256"
USER_SESSION_ISSUER = "dml-survey"
USER_SESSION_AUDIENCE = "dml-survey-user"
class ExternalUser(BaseModel):
    external_user_id: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=100)

    @field_validator("external_user_id", "username")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(unicodedata.category(character).startswith("C") for character in value):
            raise ValueError("identity text is invalid")
        return value


class ExternalTicket(BaseModel):
    user: ExternalUser
    jti: str = Field(min_length=1, max_length=200)
    expires_at: datetime
    state: str = Field(min_length=32, max_length=200)


class ExternalIdentityClaims(BaseModel):
    itcode: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    realname: str = Field(min_length=1, max_length=100)
    dept: str = Field(min_length=1, max_length=300)
    external_user: bool

    @field_validator("itcode", "name", "realname", "dept")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(unicodedata.category(character).startswith("C") for character in value):
            raise ValueError("identity text is invalid")
        return value


def _configured_secret(value: str) -> bool:
    return configured_secret(value)


def sso_enabled(settings: Settings) -> bool:
    return (
        _configured_secret(settings.external_sso_shared_secret)
        and _user_session_secret_is_safe(settings)
        and settings.external_sso_shared_secret != settings.admin_session_secret
    )


def decode_external_ticket(ticket: str, settings: Settings) -> ExternalTicket:
    if not _configured_secret(settings.external_sso_shared_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="外部系统登录尚未配置",
        )
    try:
        payload: dict[str, Any] = jwt.decode(
            ticket,
            settings.external_sso_shared_secret,
            algorithms=[JWT_ALGORITHM],
            audience=settings.external_sso_audience,
            issuer=settings.external_sso_issuer,
            options={"require": ["iss", "aud", "sub", "username", "iat", "exp", "jti", "state", "token_type"]},
        )
        if payload["token_type"] != "external_sso":
            raise ValueError("ticket type is invalid")
        issued_at = datetime.fromtimestamp(float(payload["iat"]), UTC)
        expires_at = datetime.fromtimestamp(float(payload["exp"]), UTC)
        now = datetime.now(UTC)
        if issued_at > now + timedelta(seconds=5):
            raise ValueError("ticket issued in the future")
        if expires_at - issued_at > timedelta(seconds=settings.external_ticket_max_seconds):
            raise ValueError("ticket lifetime is too long")
        return ExternalTicket(
            user=ExternalUser(
                external_user_id=str(payload["sub"]),
                username=str(payload["username"]),
            ),
            jti=str(payload["jti"]),
            expires_at=expires_at,
            state=str(payload["state"]),
        )
    except (jwt.PyJWTError, KeyError, OSError, OverflowError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="外部系统登录凭证无效或已过期",
        ) from error


def decode_external_identity_token(token: str, settings: Settings) -> ExternalUser:
    """Validate the JWT issued by the external portal and map it to a local user."""
    if not _configured_secret(settings.external_sso_shared_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="外部系统登录尚未配置",
        )
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.external_sso_shared_secret,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["itcode", "name", "realname", "dept", "external_user"],
                "verify_aud": False,
                "verify_iss": False,
            },
        )
        identity = ExternalIdentityClaims.model_validate(payload)
        return ExternalUser(
            external_user_id=identity.itcode,
            username=identity.realname or identity.name,
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="外部系统登录凭证无效或已过期",
        ) from error


def create_user_session_token(user: ExternalUser, settings: Settings) -> str:
    if not _user_session_secret_is_safe(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="问卷用户会话尚未配置",
        )
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user.external_user_id,
            "username": user.username,
            "iat": now,
            "exp": now + timedelta(hours=settings.user_session_hours),
            "iss": USER_SESSION_ISSUER,
            "aud": USER_SESSION_AUDIENCE,
            "token_type": "user_session",
        },
        settings.user_session_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_user_session(token: str, settings: Settings) -> ExternalUser:
    if not _user_session_secret_is_safe(settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效")
    try:
        payload = jwt.decode(
            token,
            settings.user_session_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=USER_SESSION_ISSUER,
            audience=USER_SESSION_AUDIENCE,
            options={"require": ["sub", "username", "iat", "exp", "iss", "aud", "token_type"]},
        )
        if payload["token_type"] != "user_session":
            raise ValueError("session type is invalid")
        return ExternalUser(
            external_user_id=str(payload["sub"]),
            username=str(payload["username"]),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录后提交",
        ) from error


def _user_session_secret_is_safe(settings: Settings) -> bool:
    """Ensure the user-session key is not held by an external or admin issuer."""
    return (
        _configured_secret(settings.user_session_secret)
        and settings.user_session_secret != settings.external_sso_shared_secret
        and settings.user_session_secret != settings.admin_session_secret
    )


def optional_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExternalUser | None:
    token = request.cookies.get(USER_SESSION_COOKIE)
    return decode_user_session(token, settings) if token else None


UserDependency = Annotated[ExternalUser | None, Depends(optional_user)]


def respondent_document(user: ExternalUser | None) -> dict[str, str]:
    if user is None:
        return {"auth_type": "anonymous"}
    return {
        "auth_type": "external",
        "external_user_id": user.external_user_id,
        "username": user.username,
    }
