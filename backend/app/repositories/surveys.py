from datetime import UTC, datetime
from typing import Any

from pymongo import DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.survey_models import SurveyDraftUpdate, SurveyVersion


class SurveyRepositoryMixin:
    async def ensure_default_survey(self, published: SurveyVersion, draft: SurveyVersion) -> None:
        if self._survey_seed_ready:
            return
        async with self._survey_seed_lock:
            if self._survey_seed_ready:
                return
            now = datetime.now(UTC)
            if await self.survey_versions.find_one(
                {"survey_key": published.survey_key, "version": 1}
            ) is None:
                document = published.model_dump(exclude={"version_id"}, mode="python")
                document.update({"created_at": now, "updated_at": now, "published_at": now})
                await self.survey_versions.insert_one(document)
            if await self.survey_versions.find_one(
                {"survey_key": draft.survey_key, "status": "draft"}
            ) is None:
                document = draft.model_dump(exclude={"version_id"}, mode="python")
                document.update({"created_at": now, "updated_at": now, "published_at": None})
                await self.survey_versions.insert_one(document)
            self._survey_seed_ready = True

    async def get_current_survey(self, survey_key: str = "dml-v4") -> dict[str, Any] | None:
        return await self.survey_versions.find_one(
            {"survey_key": survey_key, "status": "published"},
            sort=[("version", DESCENDING)],
        )

    async def get_survey_version(self, version_id: str) -> dict[str, Any] | None:
        versions = await self.get_survey_versions([version_id])
        return versions[0] if versions else None

    async def get_survey_versions(self, version_ids: list[str]) -> list[dict[str, Any]]:
        object_ids = [object_id for value in version_ids if (object_id := self.object_id(value))]
        if not object_ids:
            return []
        return await self.survey_versions.find(
            {
                "_id": {"$in": object_ids},
                "status": {"$in": ["published", "archived"]},
            }
        ).to_list()

    async def get_survey_draft(self, survey_key: str) -> dict[str, Any] | None:
        return await self.survey_versions.find_one({"survey_key": survey_key, "status": "draft"})

    async def save_survey_draft(
        self,
        survey_key: str,
        update: SurveyDraftUpdate,
    ) -> dict[str, Any] | None:
        return await self.survey_versions.find_one_and_update(
            {
                "survey_key": survey_key,
                "status": "draft",
                "revision": update.revision,
            },
            {
                "$set": {
                    "title": update.title,
                    "description": update.description,
                    "roles": [role.model_dump(mode="python") for role in update.roles],
                    "pages": [page.model_dump(mode="python") for page in update.pages],
                    "updated_at": datetime.now(UTC),
                },
                "$inc": {"revision": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    async def publish_survey_draft(
        self,
        survey_key: str,
        expected_revision: int,
    ) -> dict[str, Any] | None:
        async with self._publish_lock:

            async def publish_transaction(session: Any) -> dict[str, Any] | None:
                draft = await self.survey_versions.find_one(
                    {"survey_key": survey_key, "status": "draft"},
                    session=session,
                )
                if draft is None or draft.get("revision") != expected_revision:
                    return None
                now = datetime.now(UTC)
                claimed_draft = await self.survey_versions.find_one_and_update(
                    {
                        "_id": draft["_id"],
                        "status": "draft",
                        "revision": expected_revision,
                    },
                    {"$set": {"updated_at": now}, "$inc": {"revision": 1}},
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )
                if claimed_draft is None:
                    return None
                model = self.survey_document(claimed_draft)
                model.validate_for_publish()
                latest = await self.survey_versions.find_one(
                    {"survey_key": survey_key, "version": {"$gt": 0}},
                    sort=[("version", DESCENDING)],
                    session=session,
                )
                next_version = int(latest["version"]) + 1 if latest else 1
                published = model.model_dump(exclude={"version_id"}, mode="python")
                published.update(
                    {
                        "version": next_version,
                        "status": "published",
                        "revision": 1,
                        "created_at": now,
                        "updated_at": now,
                        "published_at": now,
                        "closed_at": None,
                    }
                )
                await self.survey_versions.update_many(
                    {"survey_key": survey_key, "status": "published"},
                    {"$set": {"status": "archived", "updated_at": now}},
                    session=session,
                )
                result = await self.survey_versions.insert_one(published, session=session)
                return {**published, "_id": result.inserted_id}

            try:
                async with self.client.start_session() as session:
                    return await session.with_transaction(publish_transaction)
            except DuplicateKeyError:
                raise ValueError("问卷版本正在被其他管理员发布，请刷新后重试") from None

    async def set_survey_closed(self, survey_key: str, closed: bool) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        return await self.survey_versions.find_one_and_update(
            {"survey_key": survey_key, "status": "published"},
            {"$set": {"closed_at": now if closed else None, "updated_at": now}},
            sort=[("version", DESCENDING)],
            return_document=ReturnDocument.AFTER,
        )

    @staticmethod
    def survey_document(document: dict[str, Any]) -> SurveyVersion:
        data = {**document, "version_id": str(document["_id"])}
        data.pop("_id", None)
        return SurveyVersion.model_validate(data)

    async def list_survey_versions(self, survey_key: str) -> list[dict[str, Any]]:
        cursor = self.survey_versions.find(
            {
                "survey_key": survey_key,
                "version": {"$gt": 0},
                "status": {"$in": ["published", "archived"]},
            }
        ).sort("version", DESCENDING)
        documents = [document async for document in cursor]
        version_ids = [str(document["_id"]) for document in documents]
        counts: dict[str, int] = {}
        if version_ids:
            count_cursor = await self.submissions.aggregate(
                [
                    {"$match": {"survey_version_id": {"$in": version_ids}}},
                    {"$group": {"_id": "$survey_version_id", "count": {"$sum": 1}}},
                ]
            )
            counts = {item["_id"]: item["count"] async for item in count_cursor}
        return [
            {
                "version_id": str(document["_id"]),
                "version": document["version"],
                "status": document["status"],
                "published_at": document.get("published_at"),
                "closed_at": document.get("closed_at"),
                "submission_count": counts.get(str(document["_id"]), 0),
            }
            for document in documents
        ]

    async def submission_filter_catalog(self, survey_key: str) -> dict[str, list[dict[str, str]]]:
        cursor = self.survey_versions.find(
            {
                "survey_key": survey_key,
                "version": {"$gt": 0},
                "status": {"$in": ["published", "archived"]},
            },
            {"roles": 1, "pages": 1, "version": 1},
        ).sort("version", DESCENDING)
        roles: dict[str, dict[str, str]] = {}
        pages: dict[str, dict[str, str]] = {}
        async for document in cursor:
            for role in document.get("roles", []):
                roles.setdefault(role["id"], {"id": role["id"], "label": role["label"]})
            for page in document.get("pages", []):
                pages.setdefault(page["id"], {"id": page["id"], "name": page["name"]})
        return {"roles": list(roles.values()), "pages": list(pages.values())}
