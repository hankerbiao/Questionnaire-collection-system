import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from pymongo.errors import DuplicateKeyError

from app.models import MAX_ATTACHMENT_SIZE, AttachmentMeta, SurveySubmission
from app.survey_models import SurveyVersion

READ_CHUNK_SIZE = 256 * 1024
logger = logging.getLogger(__name__)


class SubmissionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Repository(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def find_by_survey_id(self, survey_id: str) -> dict[str, Any] | None: ...
    async def upload_attachment(self, metadata: AttachmentMeta, upload: UploadFile) -> Any: ...
    async def delete_attachment(self, file_id: Any) -> None: ...
    async def insert_submission(self, document: dict[str, Any]) -> None: ...
    async def get_survey_version(self, version_id: str) -> dict[str, Any] | None: ...


class SubmissionService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    async def submit(self, payload: SurveySubmission, files: list[UploadFile]) -> str:
        await self._validate_survey_version(payload)
        metadata_by_id = payload.attachment_map()
        uploads_by_id = self._map_uploads(files)
        if set(metadata_by_id) != set(uploads_by_id):
            missing = sorted(set(metadata_by_id) - set(uploads_by_id))
            extra = sorted(set(uploads_by_id) - set(metadata_by_id))
            detail = "附件与问卷元数据不匹配"
            if missing:
                detail += f"，缺少：{', '.join(missing)}"
            if extra:
                detail += f"，多余：{', '.join(extra)}"
            raise SubmissionError(400, detail)

        file_digests: dict[str, str] = {}
        for attachment_id, upload in uploads_by_id.items():
            file_digests[attachment_id] = await self._validate_file(metadata_by_id[attachment_id], upload)

        request_digest = self._request_digest(payload, file_digests)
        await self.repository.ensure_indexes()
        existing = await self.repository.find_by_survey_id(payload.survey_id)
        if existing:
            return self._existing_submission(existing, request_digest)

        submission_id = f"DML-{uuid4().hex[:16].upper()}"
        uploaded: list[dict[str, Any]] = []
        committed = False
        try:
            for attachment_id, upload in uploads_by_id.items():
                metadata = metadata_by_id[attachment_id]
                file_id = await self.repository.upload_attachment(metadata, upload)
                uploaded.append({
                    "attachment_id": metadata.id,
                    "question_id": metadata.question_id,
                    "gridfs_id": file_id,
                    "original_name": metadata.name,
                    "content_type": metadata.type,
                    "size": metadata.size,
                })
            await self.repository.insert_submission({
                "submission_id": submission_id,
                "survey_id": payload.survey_id,
                "survey_version_id": payload.survey_version_id,
                "request_digest": request_digest,
                "submitted_at": payload.submitted_at,
                "received_at": datetime.now(UTC),
                "payload": payload.model_dump(by_alias=True, mode="json"),
                "attachments": uploaded,
            })
            committed = True
        except DuplicateKeyError:
            existing = await self.repository.find_by_survey_id(payload.survey_id)
            if existing:
                return self._existing_submission(existing, request_digest)
            raise
        finally:
            if not committed and uploaded:
                cleanup_task = asyncio.create_task(self._cleanup(uploaded))
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    await cleanup_task
                    raise
        return submission_id

    async def _validate_survey_version(self, payload: SurveySubmission) -> SurveyVersion:
        document = await self.repository.get_survey_version(payload.survey_version_id)
        if document is None:
            raise SubmissionError(400, "问卷版本不存在或尚未发布")
        version = SurveyVersion.model_validate({**document, "versionId": str(document["_id"])})
        enabled_pages = {page.id: page for page in version.pages if page.enabled}
        enabled_roles = {role.id for role in version.roles}

        invalid_roles = set(payload.profile.role_ids) - enabled_roles
        if invalid_roles:
            raise SubmissionError(422, "提交包含无效角色")
        if len(payload.top_page_ids) != 3 or set(payload.top_page_ids) - set(enabled_pages):
            raise SubmissionError(422, "必须从启用页面中恰好选择 3 个重点页面")

        for review in payload.top_page_reviews:
            page = enabled_pages[review.page_id]
            expected_features = {feature.id for feature in page.features if feature.enabled}
            if set(review.feature_scores) != expected_features:
                raise SubmissionError(422, f"页面“{page.name}”的功能点评分不完整或包含无效功能")

        max_score = max(review.overall_score for review in payload.top_page_reviews)
        highest_page_ids = {
            review.page_id for review in payload.top_page_reviews if review.overall_score == max_score
        }
        if payload.favorite_page_review.page_id not in highest_page_ids:
            raise SubmissionError(422, "最高分页复盘必须选择综合分最高的页面")

        expected_other_ids = set(enabled_pages) - set(payload.top_page_ids)
        actual_other_ids = {review.page_id for review in payload.other_page_reviews}
        if actual_other_ids != expected_other_ids:
            raise SubmissionError(422, "其余页面评价必须完整覆盖所有非重点页面")

        attachment_ids = set(payload.attachment_map())
        if len(attachment_ids) != len(payload.issue_evidence.attachments):
            raise SubmissionError(400, "附件 ID 不可重复")
        return version

    @staticmethod
    def _map_uploads(files: list[UploadFile]) -> dict[str, UploadFile]:
        uploads: dict[str, UploadFile] = {}
        for upload in files:
            attachment_id = upload.filename or ""
            if not attachment_id:
                raise SubmissionError(400, "附件缺少 ID 文件名")
            if attachment_id in uploads:
                raise SubmissionError(400, f"附件 ID 重复：{attachment_id}")
            uploads[attachment_id] = upload
        return uploads

    @staticmethod
    async def _validate_file(metadata: AttachmentMeta, upload: UploadFile) -> str:
        if upload.content_type != metadata.type:
            raise SubmissionError(400, f"附件 {metadata.id} 的 MIME 类型与元数据不一致")
        actual_size = 0
        digest = hashlib.sha256()
        signature = b""
        while chunk := await upload.read(READ_CHUNK_SIZE):
            actual_size += len(chunk)
            if actual_size > MAX_ATTACHMENT_SIZE:
                raise SubmissionError(413, f"附件 {metadata.id} 超过 5 MB")
            digest.update(chunk)
            if len(signature) < 12:
                signature += chunk[: 12 - len(signature)]
        await upload.seek(0)
        if actual_size != metadata.size:
            raise SubmissionError(400, f"附件 {metadata.id} 的大小与元数据不一致")
        if not SubmissionService._has_valid_signature(metadata.type, signature):
            raise SubmissionError(400, f"附件 {metadata.id} 不是有效的图片文件")
        try:
            await asyncio.to_thread(SubmissionService._verify_image, upload.file, metadata.type)
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
            raise SubmissionError(400, f"附件 {metadata.id} 不是有效的图片文件") from error
        await upload.seek(0)
        return digest.hexdigest()

    @staticmethod
    def _has_valid_signature(content_type: str, signature: bytes) -> bool:
        if content_type == "image/png":
            return signature.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/jpeg":
            return signature.startswith(b"\xff\xd8\xff")
        if content_type == "image/webp":
            return signature.startswith(b"RIFF") and signature[8:12] == b"WEBP"
        return False

    @staticmethod
    def _verify_image(source: Any, content_type: str) -> None:
        expected_format = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[content_type]
        Image.MAX_IMAGE_PIXELS = 25_000_000
        with Image.open(source) as image:
            if image.format != expected_format:
                raise ValueError("image format does not match content type")
            width, height = image.size
            if width > 10_000 or height > 10_000 or width * height > 25_000_000:
                raise ValueError("image dimensions are too large")
            image.verify()

    @staticmethod
    def _request_digest(payload: SurveySubmission, file_digests: dict[str, str]) -> str:
        payload_data = payload.model_dump(by_alias=True, mode="json")
        payload_data.pop("submittedAt", None)
        canonical = json.dumps(
            {"payload": payload_data, "files": file_digests},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _existing_submission(existing: dict[str, Any], request_digest: str) -> str:
        if existing.get("request_digest") != request_digest:
            raise SubmissionError(409, "该问卷 ID 已提交过不同内容")
        return str(existing["submission_id"])

    async def _cleanup(self, uploaded: list[dict[str, Any]]) -> None:
        results = await asyncio.gather(
            *(self.repository.delete_attachment(item["gridfs_id"]) for item in uploaded),
            return_exceptions=True,
        )
        for item, result in zip(uploaded, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Failed to clean up orphaned GridFS attachment %s: %s", item["gridfs_id"], result)
