import os
from io import BytesIO
from typing import Any
from uuid import uuid4

import pytest
from fastapi import UploadFile
from pymongo import AsyncMongoClient
from starlette.datastructures import Headers

from app.models import SurveySubmission
from app.repository import SubmissionRepository
from app.services import SubmissionService
from app.default_survey import default_survey
from tests.test_models import attachment, submission_data
from tests.test_services import PNG_BYTES

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MONGO_INTEGRATION") != "1",
    reason="set RUN_MONGO_INTEGRATION=1 to use the dedicated MongoDB test database",
)


class FailingInsertCollection:
    def __init__(self, collection: Any) -> None:
        self.collection = collection

    def __getattr__(self, name: str) -> Any:
        return getattr(self.collection, name)

    async def insert_one(self, document: dict[str, Any], **kwargs: Any) -> None:
        raise RuntimeError("injected publication insert failure")


async def test_real_mongodb_submission_round_trip() -> None:
    client = AsyncMongoClient(os.getenv("MONGODB_URI", "mongodb://10.17.154.252:27019"))
    database_name = f"dml_v4_survey_test_{uuid4().hex}"
    repository = SubmissionRepository(client, database_name)
    data = submission_data()
    data["surveyId"] = "integration-survey"
    data["issueEvidence"] = {
        "description": "问题说明",
        "attachments": [attachment("integration-file")],
    }
    upload = UploadFile(
        file=BytesIO(PNG_BYTES),
        filename="integration-file",
        headers=Headers({"content-type": "image/png"}),
    )
    try:
        await repository.ensure_indexes()
        await repository.ensure_default_survey(default_survey("published", 1), default_survey("draft", 0))
        published = await repository.get_current_survey()
        data["surveyVersionId"] = str(published["_id"])
        submission_id = await SubmissionService(repository).submit(
            SurveySubmission.model_validate(data),
            [upload],
        )
        stored = await repository.submissions.find_one({"survey_id": "integration-survey"})
        assert stored is not None
        assert stored["submission_id"] == submission_id
        assert await repository.database["survey_attachments.files"].count_documents({}) == 1
    finally:
        try:
            await client.drop_database(database_name)
        finally:
            await client.close()


async def test_real_mongodb_publication_transaction() -> None:
    client = AsyncMongoClient(os.getenv("MONGODB_URI", "mongodb://10.17.154.252:27019"))
    database_name = f"dml_v4_survey_publish_test_{uuid4().hex}"
    repository = SubmissionRepository(client, database_name)
    try:
        await repository.ensure_indexes()
        await repository.ensure_default_survey(default_survey("published", 1), default_survey("draft", 0))

        published = await repository.publish_survey_draft("dml-v4", expected_revision=1)

        assert published is not None
        assert published["version"] == 2
        assert await repository.survey_versions.count_documents({"status": "published"}) == 1
        assert await repository.survey_versions.count_documents({"status": "archived"}) == 1
        draft = await repository.get_survey_draft("dml-v4")
        assert draft is not None
        assert draft["revision"] == 2
        assert "publishing_token" not in draft
    finally:
        try:
            await client.drop_database(database_name)
        finally:
            await client.close()


async def test_real_mongodb_publication_transaction_rolls_back_on_insert_failure() -> None:
    client = AsyncMongoClient(os.getenv("MONGODB_URI", "mongodb://10.17.154.252:27019"))
    database_name = f"dml_v4_rollback_{uuid4().hex}"
    repository = SubmissionRepository(client, database_name)
    try:
        await repository.ensure_indexes()
        await repository.ensure_default_survey(default_survey("published", 1), default_survey("draft", 0))
        collection = repository.survey_versions
        repository.survey_versions = FailingInsertCollection(collection)

        with pytest.raises(RuntimeError, match="injected publication insert failure"):
            await repository.publish_survey_draft("dml-v4", expected_revision=1)

        assert await collection.count_documents({}) == 2
        assert await collection.count_documents({"status": "published"}) == 1
        assert await collection.count_documents({"status": "archived"}) == 0
        draft = await collection.find_one({"status": "draft"})
        assert draft is not None
        assert draft["revision"] == 1
    finally:
        try:
            await client.drop_database(database_name)
        finally:
            await client.close()
