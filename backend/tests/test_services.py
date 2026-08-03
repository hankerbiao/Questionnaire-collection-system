from base64 import b64decode
from copy import deepcopy
from io import BytesIO
from typing import Any

import pytest
from bson import ObjectId
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.default_survey import default_survey
from app.models import SurveySubmission
from app.services import SubmissionError, SubmissionService
from tests.test_models import VERSION_ID, attachment, submission_data

PNG_BYTES = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


class FakeRepository:
    def __init__(self) -> None:
        self.existing: dict[str, Any] | None = None
        self.uploaded: list[str] = []
        self.deleted: list[str] = []
        self.document: dict[str, Any] | None = None
        self.insert_error: Exception | None = None
        self.version_document: dict[str, Any] | None = published_version_document()
        self.current_survey: dict[str, Any] | None = published_version_document()
        self.owned: bool = True
        self.updated: dict[str, Any] | None = None

    async def ensure_indexes(self) -> None: pass
    async def find_by_survey_id(self, survey_id: str) -> dict[str, Any] | None: return self.existing
    async def upload_attachment(self, metadata: Any, upload: UploadFile) -> str:
        value = f"gridfs-{metadata.id}"; self.uploaded.append(value); return value
    async def delete_attachment(self, file_id: str) -> None: self.deleted.append(file_id)
    async def insert_submission(self, document: dict[str, Any]) -> None:
        if self.insert_error: raise self.insert_error
        self.document = document
    async def get_survey_version(self, version_id: str) -> dict[str, Any] | None: return self.version_document
    async def get_current_survey(self, survey_key: str = "dml-v4") -> dict[str, Any] | None: return self.current_survey
    async def get_owned_submission(self, submission_id: str, external_user_id: str) -> dict[str, Any] | None:
        return self.existing if self.owned else None
    async def replace_submission_payload(
        self,
        *,
        submission_id: str,
        external_user_id: str,
        expected_version: int,
        payload: dict[str, Any],
        attachments: list[dict[str, Any]],
        request_digest: str,
        snapshot: dict[str, Any],
        submitted_at: Any,
    ) -> dict[str, Any] | None:
        base = dict(self.existing or {})
        base.update({
            "payload": payload,
            "attachments": attachments,
            "request_digest": request_digest,
            "submitted_at": submitted_at,
            "version": expected_version + 1,
        })
        revisions = list(base.get("revisions", []))
        revisions.append(snapshot)
        base["revisions"] = revisions
        self.updated = base
        return base


def published_version_document() -> dict[str, Any]:
    document = default_survey("published", 1).model_dump(mode="python")
    document["_id"] = ObjectId(VERSION_ID)
    return document


def upload_file(attachment_id: str, content: bytes = PNG_BYTES) -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=attachment_id, headers=Headers({"content-type": "image/png"}))


def payload(data: dict | None = None) -> SurveySubmission:
    return SurveySubmission.model_validate(data or submission_data())


async def test_valid_submission_is_stored() -> None:
    repository = FakeRepository()
    result = await SubmissionService(repository).submit(payload(), [])
    assert result.startswith("DML-")
    assert repository.document["payload"]["schemaVersion"] == 1
    assert repository.document["respondent"] == {"auth_type": "anonymous"}


async def test_authenticated_respondent_is_stored_and_affects_idempotency() -> None:
    repository = FakeRepository()
    respondent = {"auth_type": "external", "external_user_id": "demo-1", "username": "张三"}
    await SubmissionService(repository).submit(payload(), [], respondent)
    assert repository.document["respondent"] == respondent
    anonymous_digest = SubmissionService._request_digest(payload(), {}, {"auth_type": "anonymous"})
    external_digest = SubmissionService._request_digest(payload(), {}, respondent)
    assert anonymous_digest != external_digest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["profile"].update(roleIds=["invalid"]), "无效角色"),
        (lambda data: data["topPageIds"].__setitem__(0, "invalid"), "恰好选择 3 个"),
        (lambda data: data["topPageReviews"][0]["featureScores"].pop(next(iter(data["topPageReviews"][0]["featureScores"]))), "功能点评分不完整"),
        (lambda data: data["favoritePageReview"].update(pageId=data["topPageIds"][2]), "综合分最高"),
        (lambda data: data["otherPageReviews"].pop(), "完整覆盖"),
    ],
)
async def test_rejects_forged_catalog_data(mutation, message: str) -> None:
    data = deepcopy(submission_data())
    mutation(data)
    if data["topPageIds"] != [review["pageId"] for review in data["topPageReviews"]]:
        data["topPageReviews"][0]["pageId"] = data["topPageIds"][0]
    with pytest.raises(SubmissionError, match=message):
        await SubmissionService(FakeRepository()).submit(payload(data), [])


async def test_stores_verified_screenshot_and_rejects_missing_upload() -> None:
    data = submission_data()
    data["issueEvidence"] = {"description": "问题说明", "attachments": [attachment("screen-1")]}
    with pytest.raises(SubmissionError, match="缺少"):
        await SubmissionService(FakeRepository()).submit(payload(data), [])
    repository = FakeRepository()
    await SubmissionService(repository).submit(payload(data), [upload_file("screen-1")])
    assert repository.uploaded == ["gridfs-screen-1"]


async def test_cleans_up_screenshot_if_insert_fails() -> None:
    data = submission_data()
    data["issueEvidence"] = {"description": "问题说明", "attachments": [attachment("screen-1")]}
    repository = FakeRepository(); repository.insert_error = RuntimeError("insert failed")
    with pytest.raises(RuntimeError):
        await SubmissionService(repository).submit(payload(data), [upload_file("screen-1")])
    assert repository.deleted == ["gridfs-screen-1"]


def test_rejects_images_above_pixel_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class OversizedImage:
        format = "PNG"; size = (6_000, 5_000)
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def verify(self): return None
    monkeypatch.setattr(Image, "open", lambda source: OversizedImage())
    with pytest.raises(ValueError, match="dimensions"):
        SubmissionService._verify_image(BytesIO(PNG_BYTES), "image/png")


def owned_submission_document() -> dict[str, Any]:
    return {
        "survey_id": "survey-1",
        "survey_version_id": VERSION_ID,
        "submission_id": "DML-EDIT-1",
        "version": 1,
        "revisions": [],
        "attachments": [],
        "request_digest": "original",
        "submitted_at": "2026-07-24T02:00:00Z",
        "respondent": {"auth_type": "external", "external_user_id": "demo-1", "username": "张三"},
    }


async def test_edit_stores_new_payload_and_records_revision() -> None:
    repository = FakeRepository()
    repository.existing = owned_submission_document()
    result = await SubmissionService(repository).edit("DML-EDIT-1", payload(), [], "demo-1", expected_version=1)
    assert repository.updated is not None
    assert repository.updated["version"] == 2
    assert len(repository.updated["revisions"]) == 1
    assert repository.updated["revisions"][0]["request_digest"] == "original"
    assert result["version"] == 2


async def test_edit_rejects_stale_expected_version() -> None:
    repository = FakeRepository()
    repository.existing = owned_submission_document()
    with pytest.raises(SubmissionError, match="其他窗口"):
        await SubmissionService(repository).edit("DML-EDIT-1", payload(), [], "demo-1", expected_version=2)


async def test_edit_rejects_when_survey_closed() -> None:
    repository = FakeRepository()
    repository.existing = owned_submission_document()
    closed = published_version_document()
    closed["closed_at"] = "2026-08-03T00:00:00Z"
    repository.current_survey = closed
    repository.version_document = closed
    with pytest.raises(SubmissionError, match="已截止"):
        await SubmissionService(repository).edit("DML-EDIT-1", payload(), [], "demo-1", expected_version=1)


async def test_edit_rejects_unowned_submission() -> None:
    repository = FakeRepository()
    repository.existing = owned_submission_document()
    repository.owned = False
    with pytest.raises(SubmissionError, match="不存在"):
        await SubmissionService(repository).edit("DML-EDIT-1", payload(), [], "other-user", expected_version=1)


async def test_submit_rejects_closed_survey() -> None:
    repository = FakeRepository()
    closed = published_version_document()
    closed["closed_at"] = "2026-08-03T00:00:00Z"
    repository.version_document = closed
    with pytest.raises(SubmissionError, match="已截止"):
        await SubmissionService(repository).submit(payload(), [])
