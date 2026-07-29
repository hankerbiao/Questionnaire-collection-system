import json

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import router
from app.config import Settings, get_settings
from tests.test_models import submission_data
from tests.test_services import FakeRepository
from app.user_auth import ExternalUser, USER_SESSION_COOKIE, create_user_session_token


def make_app() -> FastAPI:
    app = FastAPI(); app.state.repository = FakeRepository(); app.include_router(router); return app


async def test_liveness_and_removed_route() -> None:
    async with AsyncClient(transport=ASGITransport(app=make_app()), base_url="http://test") as client:
        assert (await client.get("/api/v1/health/live")).json() == {"status": "ok"}
        removed_path = "/api/v1/" + "ai" + "/follow-up"
        assert (await client.post(removed_path, json={})).status_code == 404


async def test_submission_endpoint_uses_new_payload() -> None:
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/submissions", data={"payload": json.dumps(submission_data())})
    assert response.status_code == 201
    assert response.json()["submissionId"].startswith("DML-")
    assert app.state.repository.document["respondent"] == {"auth_type": "anonymous"}


async def test_submission_endpoint_rejects_old_or_empty_payload() -> None:
    async with AsyncClient(transport=ASGITransport(app=make_app()), base_url="http://test") as client:
        response = await client.post("/api/v1/submissions", data={"payload": "{}"})
    assert response.status_code == 422


async def test_submission_uses_verified_session_identity() -> None:
    settings = Settings(user_session_secret="user-session-secret-that-is-long-enough")
    app = make_app()
    app.dependency_overrides[get_settings] = lambda: settings
    token = create_user_session_token(
        ExternalUser(external_user_id="demo-1", username="张三"),
        settings,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(USER_SESSION_COOKIE, token)
        response = await client.post(
            "/api/v1/submissions",
            headers={"Origin": "http://test"},
            data={"payload": json.dumps(submission_data())},
        )
    assert response.status_code == 201
    assert app.state.repository.document["respondent"] == {
        "auth_type": "external",
        "external_user_id": "demo-1",
        "username": "张三",
    }


async def test_authenticated_submission_rejects_foreign_origin() -> None:
    settings = Settings(user_session_secret="user-session-secret-that-is-long-enough")
    app = make_app()
    app.dependency_overrides[get_settings] = lambda: settings
    token = create_user_session_token(ExternalUser(external_user_id="demo-1", username="张三"), settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(USER_SESSION_COOKIE, token)
        response = await client.post(
            "/api/v1/submissions",
            headers={"Origin": "http://evil.test"},
            data={"payload": json.dumps(submission_data())},
        )
    assert response.status_code == 403
