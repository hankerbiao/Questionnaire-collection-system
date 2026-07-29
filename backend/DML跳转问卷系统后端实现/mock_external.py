from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from html import escape
import os
import unicodedata
from urllib.parse import urlencode
from uuid import uuid4

import jwt
from fastapi import FastAPI, Form, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

# Copy these values from the questionnaire backend configuration before use.
JWT_ALGORITHM = "HS256"
# Keep the secret outside the distributed source file.
EXTERNAL_SSO_SHARED_SECRET = os.getenv("EXTERNAL_SSO_SHARED_SECRET")
# Must be identical to the questionnaire's EXTERNAL_SSO_ISSUER.
EXTERNAL_SSO_ISSUER = "dml-demo-external"
# Must be identical to the questionnaire's EXTERNAL_SSO_AUDIENCE.
EXTERNAL_SSO_AUDIENCE = "dml-survey"
# The questionnaire callback URL that receives the signed ticket.
SURVEY_CALLBACK_URL = "http://10.17.158.73:8280/api/v1/auth/external/callback"
# The questionnaire URL that starts the browser-bound state flow.
SURVEY_LOGIN_START_URL = "http://10.17.158.73:8280/api/v1/auth/external/start"
# The ticket lifetime; it must match the questionnaire's allowed maximum.
EXTERNAL_TICKET_MAX_SECONDS: int = 60
UNSAFE_SECRETS = {
    "change-me-in-production",
    "replace-with-at-least-32-random-characters",
    "replace-with-another-32-character-random-secret",
    "replace-with-a-user-session-random-secret",
    "use-a-different-at-least-32-character-secret",
}


@dataclass(frozen=True)
class ExternalUser:
    external_user_id: str
    username: str


def _validate_configuration() -> int:
    """在签发票据前检查单文件工具必须填写的常量配置。"""
    required = {
        "EXTERNAL_SSO_ISSUER": EXTERNAL_SSO_ISSUER,
        "EXTERNAL_SSO_AUDIENCE": EXTERNAL_SSO_AUDIENCE,
        "SURVEY_CALLBACK_URL": SURVEY_CALLBACK_URL,
        "SURVEY_LOGIN_START_URL": SURVEY_LOGIN_START_URL,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if not EXTERNAL_SSO_SHARED_SECRET:
        missing.append("EXTERNAL_SSO_SHARED_SECRET")
    if EXTERNAL_TICKET_MAX_SECONDS is None:
        missing.append("EXTERNAL_TICKET_MAX_SECONDS")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"请在 mock_external.py 顶部配置：{', '.join(missing)}",
        )
    if len(EXTERNAL_SSO_SHARED_SECRET) < 32 or EXTERNAL_SSO_SHARED_SECRET in UNSAFE_SECRETS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EXTERNAL_SSO_SHARED_SECRET 必须是至少 32 字符的非示例随机值",
        )
    if not isinstance(EXTERNAL_TICKET_MAX_SECONDS, int) or not 30 <= EXTERNAL_TICKET_MAX_SECONDS <= 300:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EXTERNAL_TICKET_MAX_SECONDS 必须在 30 到 300 秒之间",
        )
    return EXTERNAL_TICKET_MAX_SECONDS


def _clean_identity(value: str, max_length: int) -> str:
    """清理并校验即将写入 JWT 的用户身份字段。"""
    value = value.strip()
    if (
        not value
        or len(value) > max_length
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        raise ValueError("identity text is invalid")
    return value


def _external_user(external_user_id: str, username: str) -> ExternalUser:
    """构造问卷系统会收到的最小用户身份对象。"""
    return ExternalUser(
        external_user_id=_clean_identity(external_user_id, 128),
        username=_clean_identity(username, 100),
    )


app = FastAPI(title="Mock External System")


@app.get("/", response_class=HTMLResponse)
async def index(state: str | None = Query(default=None, min_length=32, max_length=200)) -> Response:
    """显示模拟用户表单；首次访问时跳转问卷以获取 state。"""
    _validate_configuration()
    if state is None:
        return RedirectResponse(SURVEY_LOGIN_START_URL, status_code=status.HTTP_303_SEE_OTHER)
    content = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>模拟外部系统</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f6f4;font:15px system-ui;color:#17201d}
main{width:min(420px,calc(100% - 40px));padding:28px;background:#fff;border:1px solid #d9dfdc;border-radius:8px}
h1{margin:0 0 8px;font-size:24px}p{margin:0 0 24px;color:#66716d}label{display:block;margin-top:14px;font-weight:600}
input{box-sizing:border-box;width:100%;height:42px;margin-top:7px;padding:0 11px;border:1px solid #c7d0cc;border-radius:5px;font:inherit}
button{width:100%;height:44px;margin-top:24px;border:0;border-radius:5px;background:#176b52;color:#fff;font:inherit;font-weight:600;cursor:pointer}
</style></head><body><main><h1>模拟外部系统</h1><p>填写用户信息后跳转到问卷。</p>
<form method="post" action="/launch"><input type="hidden" name="state" value="__STATE__"><label>用户 ID<input name="external_user_id" value="demo-1001" maxlength="128" required></label>
<label>username<input name="username" value="张三" maxlength="100" required></label><button>进入问卷</button></form>
</main></body></html>"""
    return HTMLResponse(content.replace("__STATE__", escape(state)))


@app.post("/launch")
async def launch(
    external_user_id: str = Form(min_length=1, max_length=128),
    username: str = Form(min_length=1, max_length=100),
    state: str = Form(min_length=32, max_length=200),
) -> RedirectResponse:
    """签发外部用户票据，并将浏览器跳转回问卷回调地址。"""
    ticket_max_seconds = _validate_configuration()
    try:
        user = _external_user(external_user_id, username)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="用户信息格式无效",
        ) from error
    now = datetime.now(UTC)
    ticket = jwt.encode(
        {
            "iss": EXTERNAL_SSO_ISSUER,
            "aud": EXTERNAL_SSO_AUDIENCE,
            "sub": user.external_user_id,
            "username": user.username,
            "iat": now,
            "exp": now + timedelta(seconds=ticket_max_seconds),
            "jti": uuid4().hex,
            "state": state,
            "token_type": "external_sso",
        },
        EXTERNAL_SSO_SHARED_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    separator = "&" if "?" in SURVEY_CALLBACK_URL else "?"
    return RedirectResponse(
        f"{SURVEY_CALLBACK_URL}{separator}{urlencode({'ticket': ticket})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


if __name__ == "__main__":
    import uvicorn

    _validate_configuration()
    uvicorn.run(app, host="127.0.0.1", port=9000)
