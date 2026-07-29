import secrets
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.api import get_repository
from app.auth import enforce_same_origin
from app.config import Settings, get_settings
from app.user_auth import (
    USER_SESSION_COOKIE,
    LOGIN_STATE_COOKIE,
    create_user_session_token,
    decode_external_ticket,
    optional_user,
    sso_enabled,
)

router = APIRouter(prefix="/api/v1/auth")


def _with_query_value(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = [(item_key, item_value) for item_key, item_value in parse_qsl(parts.query) if item_key != key]
    query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@router.get("/external/start")
async def external_start(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    if not sso_enabled(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="外部系统登录尚未配置",
        )
    state_value = secrets.token_urlsafe(32)
    response = RedirectResponse(
        _with_query_value(settings.external_portal_url, "state", state_value),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        LOGIN_STATE_COOKIE,
        state_value,
        max_age=300,
        httponly=True,
        secure=settings.user_secure_cookie,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/external/callback")
async def external_callback(
    request: Request,
    ticket: Annotated[str, Query(min_length=1, max_length=4_096)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    if not sso_enabled(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="外部系统登录尚未配置",
        )
    identity = decode_external_ticket(ticket, settings)
    expected_state = request.cookies.get(LOGIN_STATE_COOKIE)
    if not expected_state or not secrets.compare_digest(expected_state, identity.state):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="外部系统登录流程无效或已过期",
        )
    session_token = create_user_session_token(identity.user, settings)
    repository = get_repository(request)
    try:
        await repository.ensure_indexes()
        await repository.consume_external_ticket(identity.jti, identity.expires_at)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="外部系统登录凭证已使用",
        ) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂时不可用",
        ) from error

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        USER_SESSION_COOKIE,
        session_token,
        max_age=settings.user_session_hours * 3600,
        httponly=True,
        secure=settings.user_secure_cookie,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(LOGIN_STATE_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/session")
async def session(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    try:
        user = optional_user(request, settings)
    except HTTPException:
        response.delete_cookie(USER_SESSION_COOKIE, path="/")
        user = None
    return {
        "authenticated": user is not None,
        "user": (
            {"externalUserId": user.external_user_id, "username": user.username}
            if user else None
        ),
        "ssoEnabled": sso_enabled(settings),
        "loginUrl": "/api/v1/auth/external/start" if sso_enabled(settings) else None,
    }


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, str]:
    enforce_same_origin(request)
    response.delete_cookie(USER_SESSION_COOKIE, path="/")
    return {"status": "ok"}
