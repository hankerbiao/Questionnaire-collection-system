import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.default_survey import default_survey
from app.repository import SubmissionRepository


class FakeSession:
    def __init__(self) -> None:
        self.transaction_calls = 0

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def with_transaction(self, callback):
        self.transaction_calls += 1
        return await callback(self)


async def test_publish_does_not_insert_when_draft_revision_claim_is_lost() -> None:
    repository = object.__new__(SubmissionRepository)
    repository._publish_lock = asyncio.Lock()
    session = FakeSession()
    repository.client = MagicMock()
    repository.client.start_session.return_value = session
    repository.survey_versions = AsyncMock()
    draft = default_survey("draft", 0).model_dump(mode="python")
    draft.update({"_id": "draft-id", "revision": 4})
    repository.survey_versions.find_one = AsyncMock(return_value=draft)
    repository.survey_versions.find_one_and_update = AsyncMock(return_value=None)

    published = await repository.publish_survey_draft("dml-v4", expected_revision=4)

    assert published is None
    repository.survey_versions.insert_one.assert_not_awaited()
    claim = repository.survey_versions.find_one_and_update.await_args.args[0]
    assert claim["revision"] == 4
    assert session.transaction_calls == 1


def publication_repository() -> tuple[SubmissionRepository, MagicMock, FakeSession]:
    repository = object.__new__(SubmissionRepository)
    repository._publish_lock = asyncio.Lock()
    session = FakeSession()
    repository.client = MagicMock()
    repository.client.start_session.return_value = session
    collection = MagicMock()
    draft = default_survey("draft", 0).model_dump(mode="python")
    draft.update({"_id": "draft-id", "revision": 4})
    claimed_draft = {**draft, "revision": 5}
    collection.find_one = AsyncMock(side_effect=[draft, {"version": 1}])
    collection.find_one_and_update = AsyncMock(return_value=claimed_draft)
    collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id="candidate-id"))
    collection.update_many = AsyncMock(return_value=SimpleNamespace(modified_count=1))
    repository.survey_versions = collection
    return repository, collection, session


async def test_publish_archives_previous_version_and_inserts_new_version_in_transaction() -> None:
    repository, collection, session = publication_repository()

    published = await repository.publish_survey_draft("dml-v4", expected_revision=4)

    assert published is not None
    assert published["_id"] == "candidate-id"
    assert published["version"] == 2
    assert published["status"] == "published"
    inserted = collection.insert_one.await_args.args[0]
    assert inserted["status"] == "published"
    assert collection.update_many.await_count == 1
    assert collection.update_many.await_args.kwargs["session"] is session
    assert collection.insert_one.await_args.kwargs["session"] is session
    claim_update = collection.find_one_and_update.await_args.args[1]
    assert claim_update["$inc"] == {"revision": 1}
    assert session.transaction_calls == 1


async def test_publish_transaction_aborts_before_inserting_candidate_when_archive_fails() -> None:
    repository, collection, session = publication_repository()
    collection.update_many.side_effect = RuntimeError("archive failed")

    with pytest.raises(RuntimeError, match="archive failed"):
        await repository.publish_survey_draft("dml-v4", expected_revision=4)

    collection.insert_one.assert_not_awaited()
    assert collection.update_many.await_args.kwargs["session"] is session
    assert session.transaction_calls == 1
