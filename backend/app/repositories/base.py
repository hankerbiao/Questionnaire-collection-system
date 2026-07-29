import asyncio
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import AsyncGridFSBucket
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient


class RepositoryBase:
    def __init__(self, client: AsyncMongoClient, database_name: str) -> None:
        self.client = client
        self.database = client[database_name]
        self.submissions = self.database["submissions"]
        self.survey_versions = self.database["survey_versions"]
        self.audit_events = self.database["admin_audit_events"]
        self.consumed_external_tickets = self.database["consumed_external_tickets"]
        self.attachments = AsyncGridFSBucket(
            self.database,
            bucket_name="survey_attachments",
        )
        self._indexes_ready = False
        self._index_lock = asyncio.Lock()
        self._publish_lock = asyncio.Lock()
        self._survey_seed_ready = False
        self._survey_seed_lock = asyncio.Lock()

    async def ping(self) -> None:
        await self.client.admin.command("ping")

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        async with self._index_lock:
            if self._indexes_ready:
                return
            await self.submissions.create_index(
                [("survey_id", ASCENDING)],
                unique=True,
                name="uq_survey_id",
            )
            await self.submissions.create_index(
                [("submission_id", ASCENDING)],
                unique=True,
                name="uq_submission_id",
            )
            await self.submissions.create_index(
                [("submitted_at", ASCENDING)],
                name="ix_submitted_at",
            )
            await self.submissions.create_index(
                [("attachments.gridfs_id", ASCENDING)],
                name="ix_attachment_gridfs_id",
            )
            await self.submissions.create_index(
                [("survey_version_id", ASCENDING)],
                name="ix_survey_version_id",
            )
            await self.database["survey_attachments.files"].create_index(
                [("uploadDate", ASCENDING)],
                name="ix_upload_date",
            )
            await self.survey_versions.create_index(
                [("survey_key", ASCENDING), ("version", DESCENDING)],
                unique=True,
                name="uq_survey_version",
            )
            await self.survey_versions.create_index(
                [("survey_key", ASCENDING), ("status", ASCENDING)],
                name="ix_survey_status",
            )
            await self.audit_events.create_index(
                [("created_at", DESCENDING)],
                name="ix_audit_created_at",
            )
            await self.consumed_external_tickets.create_index(
                [("jti", ASCENDING)],
                unique=True,
                name="uq_consumed_external_ticket_jti",
            )
            await self.consumed_external_tickets.create_index(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="ttl_consumed_external_ticket",
            )
            await self.submissions.create_index(
                [("respondent.external_user_id", ASCENDING)],
                name="ix_respondent_external_user_id",
            )
            await self.submissions.create_index(
                [("respondent.username", ASCENDING)],
                name="ix_respondent_username",
            )
            self._indexes_ready = True

    @staticmethod
    def object_id(value: str) -> ObjectId | None:
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return None
