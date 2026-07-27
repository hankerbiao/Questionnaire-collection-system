import json

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import router
from tests.test_models import submission_data
from tests.test_services import FakeRepository


def make_app() -> FastAPI:
    app = FastAPI(); app.state.repository = FakeRepository(); app.include_router(router); return app


async def test_liveness_and_removed_route() -> None:
    async with AsyncClient(transport=ASGITransport(app=make_app()), base_url="http://test") as client:
        assert (await client.get("/api/v1/health/live")).json() == {"status": "ok"}
        removed_path = "/api/v1/" + "ai" + "/follow-up"
        assert (await client.post(removed_path, json={})).status_code == 404


async def test_submission_endpoint_uses_new_payload() -> None:
    async with AsyncClient(transport=ASGITransport(app=make_app()), base_url="http://test") as client:
        response = await client.post("/api/v1/submissions", data={"payload": json.dumps(submission_data())})
    assert response.status_code == 201
    assert response.json()["submissionId"].startswith("DML-")


async def test_submission_endpoint_rejects_old_or_empty_payload() -> None:
    async with AsyncClient(transport=ASGITransport(app=make_app()), base_url="http://test") as client:
        response = await client.post("/api/v1/submissions", data={"payload": "{}"})
    assert response.status_code == 422
