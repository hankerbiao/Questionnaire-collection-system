from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import DESCENDING


class SubmissionRepositoryMixin:
    async def find_by_survey_id(self, survey_id: str) -> dict[str, Any] | None:
        return await self.submissions.find_one(
            {"survey_id": survey_id},
            {"submission_id": 1, "request_digest": 1},
        )

    async def insert_submission(self, document: dict[str, Any]) -> None:
        await self.submissions.insert_one(document)

    async def write_audit(
        self,
        username: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self.audit_events.insert_one(
            {
                "username": username,
                "action": action,
                "details": details or {},
                "created_at": datetime.now(UTC),
            }
        )

    async def submission_stats(self) -> dict[str, int]:
        seven_days_ago = datetime.now(UTC) - timedelta(days=7)
        return {
            "total": await self.submissions.count_documents({}),
            "last7Days": await self.submissions.count_documents(
                {"submitted_at": {"$gte": seven_days_ago}}
            ),
            "withAttachments": await self.submissions.count_documents(
                {"attachments.0": {"$exists": True}}
            ),
        }

    async def list_submissions(
        self,
        filters: dict[str, Any],
        cursor_id: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        query = dict(filters)
        if cursor_id and (object_id := self.object_id(cursor_id)) is not None:
            query["_id"] = {"$lt": object_id}
        projection = {
            "submission_id": 1,
            "survey_id": 1,
            "survey_version_id": 1,
            "submitted_at": 1,
            "payload.profile.roleIds": 1,
            "payload.topPageIds": 1,
            "respondent": 1,
            "attachments": 1,
        }
        documents = await (
            self.submissions.find(query, projection)
            .sort("_id", DESCENDING)
            .limit(limit + 1)
            .to_list()
        )
        has_more = len(documents) > limit
        page = documents[:limit]
        next_cursor = str(page[-1]["_id"]) if has_more and page else None
        return page, next_cursor

    async def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        object_id = self.object_id(submission_id)
        query = {"_id": object_id} if object_id else {"submission_id": submission_id}
        return await self.submissions.find_one(query)

    def list_all_submissions(self, filters: dict[str, Any]):
        projection = {
            "submission_id": 1,
            "survey_id": 1,
            "survey_version_id": 1,
            "submitted_at": 1,
            "payload.profile": 1,
            "payload.topPageIds": 1,
            "payload.topPageReviews": 1,
            "payload.favoritePageReview": 1,
            "payload.otherPageReviews": 1,
            "payload.issueEvidence": 1,
            "payload.finalFeedback": 1,
            "respondent": 1,
            "attachments": 1,
        }
        return self.submissions.find(filters, projection).sort("_id", DESCENDING)
