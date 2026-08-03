import json
import re
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from gridfs.errors import NoFile
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.api import get_repository
from app.auth import enforce_same_origin
from app.models import SurveySubmission
from app.serialization import json_value
from app.services import SubmissionError, SubmissionService
from app.user_auth import RequiredUserDependency

router = APIRouter(prefix="/api/v1")
MAX_PAYLOAD_SIZE = 1024 * 1024
MINE_PAGE_SIZE = 50


@router.get("/submissions/mine")
async def my_submissions(
    request: Request,
    user: RequiredUserDependency,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = MINE_PAGE_SIZE,
) -> dict[str, object]:
    repository = get_repository(request)
    filters = {
        "respondent.external_user_id": user.external_user_id,
        "respondent.auth_type": "external",
    }
    documents, next_cursor = await repository.list_submissions(filters, cursor, limit)
    items = [
        {
            "id": str(document["_id"]),
            "submissionId": document.get("submission_id"),
            "surveyId": document.get("survey_id"),
            "surveyVersionId": document.get("survey_version_id"),
            "submittedAt": document.get("submitted_at"),
            "updatedAt": document.get("updated_at"),
            "version": int(document.get("version", 1)),
            "revisionCount": len(document.get("revisions", [])),
            "attachmentCount": len(document.get("attachments", [])),
        }
        for document in documents
    ]
    return {"items": items, "nextCursor": next_cursor}


@router.get("/submissions/{submission_id}")
async def my_submission_detail(request: Request, submission_id: str, user: RequiredUserDependency) -> dict[str, object]:
    repository = get_repository(request)
    document = await repository.get_owned_submission(submission_id, user.external_user_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交记录不存在")

    current_survey = await repository.get_current_survey()
    survey_closed = bool(current_survey and current_survey.get("closed_at") is not None)

    attachments = [
        {
            "id": str(item["gridfs_id"]),
            "attachmentId": item["attachment_id"],
            "name": item["original_name"],
            "type": item["content_type"],
            "size": item["size"],
        }
        for item in document.get("attachments", [])
    ]
    current_gridfs_ids = {str(item.get("gridfs_id")) for item in document.get("attachments", [])}
    revisions = [
        {
            "index": index,
            "editedAt": revision.get("edited_at"),
            "payload": json_value(revision.get("payload", {})),
            "attachments": [
                {
                    "id": str(item["gridfs_id"]),
                    "attachmentId": item["attachment_id"],
                    "name": item["original_name"],
                    "type": item["content_type"],
                    "size": item["size"],
                    "available": str(item.get("gridfs_id")) in current_gridfs_ids,
                }
                for item in revision.get("attachments", [])
            ],
        }
        for index, revision in enumerate(document.get("revisions", []), start=1)
    ]
    return {
        "id": str(document["_id"]),
        "submissionId": document.get("submission_id"),
        "surveyId": document.get("survey_id"),
        "surveyVersionId": document.get("survey_version_id"),
        "submittedAt": document.get("submitted_at"),
        "updatedAt": document.get("updated_at"),
        "version": int(document.get("version", 1)),
        "revisionCount": len(document.get("revisions", [])),
        "attachmentCount": len(document.get("attachments", [])),
        "payload": json_value(document.get("payload", {})),
        "attachments": attachments,
        "revisions": revisions,
        "surveyClosed": survey_closed,
    }


@router.get("/submissions/{submission_id}/attachments/{gridfs_id}")
async def my_submission_attachment(
    request: Request,
    submission_id: str,
    gridfs_id: str,
    user: RequiredUserDependency,
) -> StreamingResponse:
    repository = get_repository(request)
    document = await repository.get_owned_submission(submission_id, user.external_user_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交记录不存在")
    owned_ids = {str(item.get("gridfs_id")) for item in document.get("attachments", [])}
    for revision in document.get("revisions", []):
        for item in revision.get("attachments", []):
            owned_ids.add(str(item.get("gridfs_id")))
    if gridfs_id not in owned_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")

    stream, file_document = await repository.open_attachment(gridfs_id)
    if stream is None or file_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    metadata = file_document.get("metadata", {})
    raw_name = str(metadata.get("original_name", "attachment"))
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name) or "attachment"

    async def chunks():
        while chunk := await stream.read(256 * 1024):
            yield chunk

    return StreamingResponse(
        chunks(),
        media_type=metadata.get("content_type", "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.put("/submissions/{submission_id}")
async def edit_submission(
    request: Request,
    submission_id: str,
    user: RequiredUserDependency,
    payload: Annotated[str, Form()],
    expected_version: Annotated[int, Form(ge=1)],
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> dict[str, object]:
    enforce_same_origin(request)
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="问卷数据超过 1 MB",
        )
    try:
        parsed_payload = SurveySubmission.model_validate_json(payload)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=json.loads(error.json(include_url=False)),
        ) from error

    try:
        updated = await SubmissionService(get_repository(request)).edit(
            submission_id,
            parsed_payload,
            files or [],
            user.external_user_id,
            expected_version,
        )
    except SubmissionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂时不可用",
        ) from error

    return {"submissionId": updated.get("submission_id"), "version": int(updated.get("version", 1))}
