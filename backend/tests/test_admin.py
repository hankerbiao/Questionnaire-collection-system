from datetime import UTC, datetime

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.admin_api import CSV_HEADERS, _csv_cell, _csv_row, _filters, _summary, router
from app.default_survey import default_survey
from app.auth import ADMIN_SESSION_AUDIENCE, ADMIN_SESSION_ISSUER, LoginRequest, create_session_token, verify_login
from app.config import Settings, get_settings
from app.repository import SubmissionRepository


class FakeAdminRepository:
    def __init__(self) -> None:
        self.audits: list[str] = []

    async def write_audit(self, username: str, action: str, details=None) -> None:
        self.audits.append(action)

    async def submission_stats(self) -> dict[str, int]:
        return {"total": 3, "last7Days": 2, "withAttachments": 1}


def settings() -> Settings:
    return Settings(
        admin_username="admin",
        admin_password_hash=PasswordHash.recommended().hash("correct-password"),
        admin_session_secret="test-secret-that-is-long-enough-for-hs256",
    )


def test_login_verification_and_session_expiry() -> None:
    config = settings()
    assert verify_login(LoginRequest(username="admin", password="correct-password"), config)
    assert not verify_login(LoginRequest(username="admin", password="wrong"), config)
    payload = jwt.decode(
        create_session_token("admin", config),
        config.admin_session_secret,
        algorithms=["HS256"],
        issuer=ADMIN_SESSION_ISSUER,
        audience=ADMIN_SESSION_AUDIENCE,
    )
    assert payload["sub"] == "admin"
    assert datetime.fromtimestamp(payload["exp"], UTC) > datetime.now(UTC)


def test_admin_routes_require_authentication_and_origin() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.repository = FakeAdminRepository()
    app.dependency_overrides[get_settings] = settings
    client = TestClient(app)

    assert client.get("/api/v1/admin/submissions/stats").status_code == 401
    assert client.post(
        "/api/v1/admin/auth/login",
        json={"username": "admin", "password": "correct-password"},
    ).status_code == 403
    response = client.post(
        "/api/v1/admin/auth/login",
        headers={"Origin": "http://testserver"},
        json={"username": "admin", "password": "correct-password"},
    )
    assert response.status_code == 200
    assert response.cookies.get("dml_admin_session")
    assert client.get("/api/v1/admin/submissions/stats").json()["total"] == 3


def test_admin_rejects_user_session_token_even_when_signed_with_admin_secret() -> None:
    config = settings()
    app = FastAPI()
    app.include_router(router)
    app.state.repository = FakeAdminRepository()
    app.dependency_overrides[get_settings] = lambda: config
    client = TestClient(app)
    now = datetime.now(UTC)
    user_token = jwt.encode(
        {
            "sub": config.admin_username,
            "username": "admin",
            "iat": now,
            "exp": now.replace(year=now.year + 1),
            "iss": "dml-survey",
            "aud": "dml-survey-user",
            "token_type": "user_session",
        },
        config.admin_session_secret,
        algorithm="HS256",
    )
    client.cookies.set("dml_admin_session", user_token)
    assert client.get("/api/v1/admin/submissions/stats").status_code == 401


def test_admin_rejects_external_ticket_key_reused_as_admin_key() -> None:
    config = settings()
    config.external_sso_shared_secret = config.admin_session_secret
    app = FastAPI()
    app.include_router(router)
    app.state.repository = FakeAdminRepository()
    app.dependency_overrides[get_settings] = lambda: config
    client = TestClient(app)
    now = datetime.now(UTC)
    forged_admin_token = jwt.encode(
        {
            "sub": config.admin_username,
            "iat": now,
            "exp": now.replace(year=now.year + 1),
            "iss": ADMIN_SESSION_ISSUER,
            "aud": ADMIN_SESSION_AUDIENCE,
            "token_type": "admin_session",
        },
        config.external_sso_shared_secret,
        algorithm="HS256",
    )

    assert not verify_login(LoginRequest(username="admin", password="correct-password"), config)
    client.cookies.set("dml_admin_session", forged_admin_token)
    assert client.get("/api/v1/admin/submissions/stats").status_code == 401


def test_admin_rejects_every_public_placeholder_secret() -> None:
    for placeholder in (
        "change-me-in-production",
        "replace-with-at-least-32-random-characters",
        "replace-with-another-32-character-random-secret",
        "replace-with-a-user-session-random-secret",
        "use-a-different-at-least-32-character-secret",
    ):
        config = settings()
        config.admin_session_secret = placeholder

        assert not verify_login(LoginRequest(username="admin", password="correct-password"), config)


def test_csv_cells_neutralize_formulas() -> None:
    assert _csv_cell("=2+2") == "'=2+2"
    assert _csv_cell(" \n=2+2") == "' \n=2+2"
    assert _csv_cell("normal") == "normal"


def test_csv_export_route_is_registered_before_dynamic_detail() -> None:
    paths = [route.path for route in router.routes]
    assert paths.index("/api/v1/admin/submissions/export.csv") < paths.index(
        "/api/v1/admin/submissions/{submission_id}"
    )


def test_new_submission_filters_and_summary_use_role_and_page_fields() -> None:
    filters = _filters(None, None, None, "tester", "requirements", None, None)
    assert filters["payload.profile.roleIds"] == "tester"
    assert filters["$or"] == [
        {"payload.topPageIds": "requirements"},
        {"payload.otherPageReviews": {"$elemMatch": {"pageId": "requirements", "status": "rated"}}},
    ]
    version = default_survey("published", 1)
    item = _summary({
        "_id": "row-1",
        "submission_id": "DML-1",
        "survey_id": "survey-1",
        "survey_version_id": "version-1",
        "submitted_at": datetime.now(UTC),
        "payload": {"profile": {"roleIds": ["tester"]}, "topPageIds": ["requirements"]},
        "respondent": {"auth_type": "external", "external_user_id": "demo-1", "username": "张三"},
        "attachments": [],
    }, version)
    assert item["roles"] == ["tester"]
    assert item["pages"] == ["requirements"]
    assert item["roleNames"]["tester"] == "测试人员"
    assert item["pageNames"]["requirements"] == "测试需求"
    assert item["username"] == "张三"
    assert item["externalUserId"] == "demo-1"
    identity_filters = _filters(None, None, None, None, None, None, None, "张三", "external")
    assert identity_filters == {
        "respondent.username": "张三",
        "respondent.auth_type": "external",
    }


def test_csv_export_contains_every_fixed_flow_section() -> None:
    document = {
        "_id": "row-1",
        "submission_id": "DML-1",
        "survey_id": "survey-1",
        "survey_version_id": "version-1",
        "submitted_at": datetime.now(UTC),
        "payload": {
            "profile": {"roleIds": ["tester"], "roleContext": "context"},
            "topPageIds": ["requirements"],
            "topPageReviews": [{"pageId": "requirements"}],
            "favoritePageReview": {"pageId": "requirements", "winningReason": "reason"},
            "otherPageReviews": [{"pageId": "cases", "status": "unused"}],
            "issueEvidence": {"description": "issue"},
            "finalFeedback": "feedback",
        },
        "attachments": [],
        "respondent": {"auth_type": "external", "external_user_id": "demo-1", "username": "张三"},
    }
    row = dict(zip(CSV_HEADERS, _csv_row(document), strict=True))
    assert row["role_context"] == "context"
    assert "winningReason" in row["favorite_page_review_json"]
    assert "description" in row["issue_evidence_json"]
    assert row["final_feedback"] == "feedback"
    assert row["auth_type"] == "external"
    assert row["external_user_id"] == "demo-1"
    assert row["username"] == "张三"


def test_publish_returns_success_when_post_commit_audit_write_fails() -> None:
    class AuditFailureRepository:
        async def publish_survey_draft(self, survey_key: str, revision: int):
            document = default_survey("published", 2).model_dump(exclude={"version_id"}, mode="python")
            document["_id"] = "published-id"
            return document

        async def write_audit(self, username: str, action: str, details=None) -> None:
            raise RuntimeError("audit unavailable")

        survey_document = staticmethod(SubmissionRepository.survey_document)

    config = settings()
    app = FastAPI()
    app.include_router(router)
    app.state.repository = AuditFailureRepository()
    app.dependency_overrides[get_settings] = lambda: config
    client = TestClient(app)
    client.cookies.set("dml_admin_session", create_session_token("admin", config))

    response = client.post(
        "/api/v1/admin/surveys/dml-v4/publish?revision=1",
        headers={"Origin": "http://testserver"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 2
