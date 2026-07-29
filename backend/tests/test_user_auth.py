from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

import mock_external
from app.config import Settings, get_settings
from app.user_api import router
from app.user_auth import (
    JWT_ALGORITHM,
    LOGIN_STATE_COOKIE,
    USER_SESSION_COOKIE,
    ExternalUser,
    create_user_session_token,
    decode_external_identity_token,
    decode_external_ticket,
    decode_user_session,
)


class FakeAuthRepository:
    def __init__(self) -> None:
        self.used: set[str] = set()

    async def ensure_indexes(self) -> None:
        pass

    async def consume_external_ticket(self, jti: str, expires_at: datetime) -> None:
        if jti in self.used:
            raise DuplicateKeyError("duplicate ticket")
        self.used.add(jti)


def settings() -> Settings:
    return Settings(
        external_sso_shared_secret="external-sso-secret-that-is-long-enough",
        user_session_secret="user-session-secret-that-is-long-enough",
        external_portal_url="http://external.test",
    )


def ticket(config: Settings, jti: str = "ticket-1", state: str = "state-value-that-is-at-least-thirty-two-characters", **overrides) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": config.external_sso_issuer,
        "aud": config.external_sso_audience,
        "sub": "demo-1",
        "username": "张三",
        "iat": now,
        "exp": now + timedelta(seconds=60),
        "jti": jti,
        "state": state,
        "token_type": "external_sso",
        **overrides,
    }
    return jwt.encode(payload, config.external_sso_shared_secret, algorithm=JWT_ALGORITHM)


def identity_token(config: Settings, **overrides) -> str:
    payload = {
        "itcode": "demo-1",
        "name": "张三",
        "realname": "张三",
        "dept": "测试部",
        "external_user": False,
        **overrides,
    }
    return jwt.encode(payload, config.external_sso_shared_secret, algorithm=JWT_ALGORITHM)


def make_client() -> tuple[TestClient, Settings]:
    config = settings()
    app = FastAPI()
    app.state.repository = FakeAuthRepository()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: config
    return TestClient(app), config


def test_external_callback_sets_session_and_ticket_is_one_time() -> None:
    client, config = make_client()
    start = client.get("/api/v1/auth/external/start", follow_redirects=False)
    assert start.status_code == 303
    state_value = client.cookies.get(LOGIN_STATE_COOKIE)
    assert state_value
    value = ticket(config, state=state_value)
    response = client.get(
        "/api/v1/auth/external/callback",
        params={"ticket": value},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert response.cookies.get(USER_SESSION_COOKIE)
    assert client.get("/api/v1/auth/session").json() == {
        "authenticated": True,
        "user": {"externalUserId": "demo-1", "username": "张三"},
        "ssoEnabled": True,
        "loginUrl": None,
    }
    client.cookies.set(LOGIN_STATE_COOKIE, state_value)
    replay = client.get(
        "/api/v1/auth/external/callback",
        params={"ticket": value},
        follow_redirects=False,
    )
    assert replay.status_code == 401


def test_external_identity_token_sets_local_session() -> None:
    client, config = make_client()

    response = client.post(
        "/api/v1/auth/external/token",
        json={"token": identity_token(config)},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.cookies.get(USER_SESSION_COOKIE)
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/auth/session").json() == {
        "authenticated": True,
        "user": {"externalUserId": "demo-1", "username": "张三"},
        "ssoEnabled": True,
        "loginUrl": None,
    }


def test_external_identity_token_rejects_invalid_signature_and_expiry() -> None:
    client, config = make_client()
    forged = jwt.encode(
        {
            "itcode": "demo-1",
            "name": "张三",
            "realname": "张三",
            "dept": "测试部",
            "external_user": False,
        },
        "different-secret-that-is-long-enough",
        algorithm=JWT_ALGORITHM,
    )
    expired = identity_token(config, exp=datetime.now(UTC) - timedelta(seconds=1))

    assert client.post("/api/v1/auth/external/token", json={"token": forged}).status_code == 401
    assert client.post("/api/v1/auth/external/token", json={"token": expired}).status_code == 401


def test_external_identity_token_maps_itcode_and_realname() -> None:
    config = settings()

    user = decode_external_identity_token(
        identity_token(config, itcode="wangyy1", name="登录名", realname="王永义"),
        config,
    )

    assert user == ExternalUser(external_user_id="wangyy1", username="王永义")


def test_external_callback_requires_browser_bound_state() -> None:
    client, config = make_client()
    value = ticket(config)
    assert client.get(
        "/api/v1/auth/external/callback",
        params={"ticket": value},
        follow_redirects=False,
    ).status_code == 401
    client.cookies.set(LOGIN_STATE_COOKIE, "different-state-value-that-is-at-least-thirty-two")
    assert client.get(
        "/api/v1/auth/external/callback",
        params={"ticket": value},
        follow_redirects=False,
    ).status_code == 401


def test_external_callback_rejects_expired_or_wrongly_signed_ticket() -> None:
    client, config = make_client()
    client.get("/api/v1/auth/external/start", follow_redirects=False)
    state_value = client.cookies.get(LOGIN_STATE_COOKIE)
    assert state_value
    expired = ticket(
        config,
        jti="expired",
        state=state_value,
        iat=datetime.now(UTC) - timedelta(minutes=2),
        exp=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert client.get("/api/v1/auth/external/callback", params={"ticket": expired}).status_code == 401
    forged = jwt.encode(
        jwt.decode(ticket(config, "forged", state_value), config.external_sso_shared_secret, algorithms=[JWT_ALGORITHM], audience=config.external_sso_audience),
        "different-secret-that-is-long-enough",
        algorithm=JWT_ALGORITHM,
    )
    assert client.get("/api/v1/auth/external/callback", params={"ticket": forged}).status_code == 401


def test_minimal_external_system_issues_redirect(monkeypatch) -> None:
    config = settings()
    config.survey_callback_url = "http://survey.test/api/v1/auth/external/callback"
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_SHARED_SECRET", config.external_sso_shared_secret)
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_ISSUER", config.external_sso_issuer)
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_AUDIENCE", config.external_sso_audience)
    monkeypatch.setattr(mock_external, "SURVEY_CALLBACK_URL", config.survey_callback_url)
    monkeypatch.setattr(mock_external, "SURVEY_LOGIN_START_URL", config.survey_login_start_url)
    monkeypatch.setattr(mock_external, "EXTERNAL_TICKET_MAX_SECONDS", config.external_ticket_max_seconds)
    client = TestClient(mock_external.app)
    state_value = "state-value-that-is-at-least-thirty-two-characters"
    assert client.get("/", follow_redirects=False).status_code == 303
    assert "模拟外部系统" in client.get("/", params={"state": state_value}).text
    response = client.post(
        "/launch",
        data={"external_user_id": "demo-2", "username": "李四", "state": state_value},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith(config.survey_callback_url + "?ticket=")
    ticket_value = parse_qs(urlsplit(response.headers["location"]).query)["ticket"][0]
    payload = jwt.decode(
        ticket_value,
        config.external_sso_shared_secret,
        algorithms=[JWT_ALGORITHM],
        audience=config.external_sso_audience,
        issuer=config.external_sso_issuer,
    )
    assert payload["iss"] == config.external_sso_issuer
    assert payload["aud"] == config.external_sso_audience


def test_minimal_external_system_requires_explicit_constants(monkeypatch) -> None:
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_SHARED_SECRET", None)
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_ISSUER", "")
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_AUDIENCE", "")
    monkeypatch.setattr(mock_external, "SURVEY_CALLBACK_URL", "")
    monkeypatch.setattr(mock_external, "SURVEY_LOGIN_START_URL", "")
    monkeypatch.setattr(mock_external, "EXTERNAL_TICKET_MAX_SECONDS", None)

    response = TestClient(mock_external.app).get("/", follow_redirects=False)

    assert response.status_code == 503
    assert "EXTERNAL_SSO_SHARED_SECRET" in response.json()["detail"]
    assert "SURVEY_CALLBACK_URL" in response.json()["detail"]


def test_minimal_external_system_rejects_public_placeholder_secret(monkeypatch) -> None:
    config = settings()
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_SHARED_SECRET", "replace-with-at-least-32-random-characters")
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_ISSUER", config.external_sso_issuer)
    monkeypatch.setattr(mock_external, "EXTERNAL_SSO_AUDIENCE", config.external_sso_audience)
    monkeypatch.setattr(mock_external, "SURVEY_CALLBACK_URL", config.survey_callback_url)
    monkeypatch.setattr(mock_external, "SURVEY_LOGIN_START_URL", config.survey_login_start_url)
    monkeypatch.setattr(mock_external, "EXTERNAL_TICKET_MAX_SECONDS", config.external_ticket_max_seconds)

    response = TestClient(mock_external.app).get("/", follow_redirects=False)

    assert response.status_code == 503
    assert "非示例随机值" in response.json()["detail"]


def test_ticket_rejects_extreme_timestamps_and_public_placeholder_secrets() -> None:
    config = settings()
    malformed = ticket(config, iat=-1e100)
    try:
        decode_external_ticket(malformed, config)
    except Exception as error:
        assert getattr(error, "status_code", None) == 401
    else:
        raise AssertionError("extreme timestamp should be rejected")

    for placeholder in (
        "replace-with-another-32-character-random-secret",
        "replace-with-a-user-session-random-secret",
        "use-a-different-at-least-32-character-secret",
    ):
        invalid = settings()
        invalid.external_sso_shared_secret = placeholder
        try:
            decode_external_ticket("invalid", invalid)
        except Exception as error:
            assert getattr(error, "status_code", None) == 503
        else:
            raise AssertionError("public placeholder secret should be rejected")


def test_user_session_rejects_public_placeholder_secret() -> None:
    config = settings()
    config.user_session_secret = "use-a-different-at-least-32-character-secret"

    try:
        create_user_session_token(ExternalUser(external_user_id="demo-1", username="张三"), config)
    except Exception as error:
        assert getattr(error, "status_code", None) == 503
    else:
        raise AssertionError("public placeholder secret should be rejected")


def test_user_session_rejects_external_ticket_key_reuse() -> None:
    config = settings()
    config.user_session_secret = config.external_sso_shared_secret
    now = datetime.now(UTC)
    forged_session = jwt.encode(
        {
            "sub": "demo-1",
            "username": "张三",
            "iat": now,
            "exp": now + timedelta(hours=1),
            "iss": "dml-survey",
            "aud": "dml-survey-user",
            "token_type": "user_session",
        },
        config.external_sso_shared_secret,
        algorithm=JWT_ALGORITHM,
    )

    try:
        decode_user_session(forged_session, config)
    except Exception as error:
        assert getattr(error, "status_code", None) == 401
    else:
        raise AssertionError("reused external ticket key should not decode user sessions")


def test_external_callback_rejects_reused_external_and_user_session_keys() -> None:
    client, config = make_client()
    config.user_session_secret = config.external_sso_shared_secret
    state_value = "state-value-that-is-at-least-thirty-two-characters"
    client.cookies.set(LOGIN_STATE_COOKIE, state_value)

    response = client.get(
        "/api/v1/auth/external/callback",
        params={"ticket": ticket(config, state=state_value)},
        follow_redirects=False,
    )

    assert response.status_code == 503


def test_external_login_rejects_reused_external_and_admin_keys() -> None:
    client, config = make_client()
    config.admin_session_secret = config.external_sso_shared_secret
    state_value = "state-value-that-is-at-least-thirty-two-characters"

    start = client.get("/api/v1/auth/external/start", follow_redirects=False)
    client.cookies.set(LOGIN_STATE_COOKIE, state_value)
    callback = client.get(
        "/api/v1/auth/external/callback",
        params={"ticket": ticket(config, state=state_value)},
        follow_redirects=False,
    )

    assert start.status_code == 503
    assert callback.status_code == 503
    assert client.get("/api/v1/auth/session").json()["ssoEnabled"] is False
