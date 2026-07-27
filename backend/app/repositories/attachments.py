from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import UploadFile
from pymongo import ASCENDING

from app.models import AttachmentMeta


class AttachmentRepositoryMixin:
    async def upload_attachment(self, metadata: AttachmentMeta, upload: UploadFile) -> Any:
        return await self.attachments.upload_from_stream(
            metadata.id,
            upload,
            metadata={
                "attachment_id": metadata.id,
                "question_id": metadata.question_id,
                "original_name": metadata.name,
                "content_type": metadata.type,
                "size": metadata.size,
            },
        )

    async def delete_attachment(self, file_id: Any) -> None:
        await self.attachments.delete(file_id)

    async def open_attachment(self, gridfs_id: str):
        object_id = self.object_id(gridfs_id)
        if object_id is None:
            return None, None
        file_document = await self.database["survey_attachments.files"].find_one({"_id": object_id})
        if file_document is None:
            return None, None
        stream = await self.attachments.open_download_stream(file_document["_id"])
        return stream, file_document

    async def reconcile_orphan_attachments(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        files = await self.database["survey_attachments.files"].aggregate(
            [
                {"$match": {"uploadDate": {"$lt": cutoff}}},
                {"$sort": {"uploadDate": ASCENDING}},
                {
                    "$lookup": {
                        "from": "submissions",
                        "localField": "_id",
                        "foreignField": "attachments.gridfs_id",
                        "as": "submission_references",
                    }
                },
                {"$match": {"submission_references.0": {"$exists": False}}},
                {"$limit": 100},
                {"$project": {"_id": 1}},
            ]
        )
        deleted = 0
        async for item in files:
            await self.attachments.delete(item["_id"])
            deleted += 1
        return deleted
