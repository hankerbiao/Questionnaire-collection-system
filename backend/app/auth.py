from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.secret_policy import configured_secret

SESSION_COOKIE = "dml_admin_session"
JWT_ALGORITHM = "HS256"
ADMIN_SESSION_ISSUER = "dml-survey"
ADMIN_SESSION_AUDIENCE = "dml-survey-admin"
password_hash = PasswordHash.recommended()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class AdminIdentity(BaseModel):
    username: str


def verify_login(credentials: LoginRequest, settings: Settings) -> bool:
    if (
        not settings.admin_password_hash
        or not _admin_secret_is_safe(settings)
        or credentials.username != settings.admin_username
    ):
        return False
    try:
        return password_hash.verify(credentials.password, settings.admin_password_hash)
    except Exception:
        return False


def create_session_token(username: str, settings: Settings) -> str:
    if not _admin_secret_is_safe(settings):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="管理后台尚未配置安全密钥")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": username,
            "iat": now,
            "exp": now + timedelta(hours=settings.admin_session_hours),
            "iss": ADMIN_SESSION_ISSUER,
            "aud": ADMIN_SESSION_AUDIENCE,
            "token_type": "admin_session",
        },
        settings.admin_session_secret,
        algorithm=JWT_ALGORITHM,
    )


def require_admin(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminIdentity:
    if not _admin_secret_is_safe(settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理后台尚未配置安全密钥")
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = jwt.decode(
            token,
            settings.admin_session_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=ADMIN_SESSION_ISSUER,
            audience=ADMIN_SESSION_AUDIENCE,
            options={"require": ["sub", "iat", "exp", "iss", "aud", "token_type"]},
        )
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期") from error
    username = payload.get("sub")
    if username != settings.admin_username or payload.get("token_type") != "admin_session":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录无效")
    return AdminIdentity(username=username)


def _admin_secret_is_safe(settings: Settings) -> bool:
    """Ensure an administrator signing key cannot also be held by another issuer."""
    return (
        configured_secret(settings.admin_session_secret)
        and settings.admin_session_secret != settings.external_sso_shared_secret
        and settings.admin_session_secret != settings.user_session_secret
    )


def enforce_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    forwarded_scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",", 1)[0].strip()
    expected = f"{forwarded_scheme}://{forwarded_host}"
    if not origin or origin.rstrip("/") != expected.rstrip("/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求来源无效")


AdminDependency = Annotated[AdminIdentity, Depends(require_admin)]
