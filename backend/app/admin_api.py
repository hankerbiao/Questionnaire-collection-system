import csv
import asyncio
import io
import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime, time, timedelta
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.api import get_repository
from app.auth import (
    SESSION_COOKIE,
    AdminDependency,
    LoginRequest,
    create_session_token,
    enforce_same_origin,
    verify_login,
)
from app.config import Settings, get_settings
from app.serialization import json_value as _json_value
from app.survey_models import SurveyDraftUpdate, SurveyVersion, SurveyVersionSummary

router = APIRouter(prefix="/api/v1/admin")
logger = logging.getLogger(__name__)


def _filters(
    date_from: datetime | None,
    date_to: datetime | None,
    version_id: str | None,
    role: str | None,
    page: str | None,
    keyword: str | None,
    has_attachments: bool | None,
    username: str | None = None,
    auth_type: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if date_from or date_to:
        submitted: dict[str, datetime] = {}
        if date_from:
            submitted["$gte"] = date_from
        if date_to:
            if date_to.time() == time.min:
                submitted["$lt"] = date_to + timedelta(days=1)
            else:
                submitted["$lte"] = date_to
        query["submitted_at"] = submitted
    if version_id:
        query["survey_version_id"] = version_id
    if role:
        query["payload.profile.roleIds"] = role
    if page:
        query["$or"] = [
            {"payload.topPageIds": page},
            {
                "payload.otherPageReviews": {
                    "$elemMatch": {"pageId": page, "status": "rated"},
                }
            },
        ]
    if keyword:
        escaped = re.escape(keyword.strip())
        keyword_query = [
            {"submission_id": {"$regex": escaped, "$options": "i"}},
            {"survey_id": {"$regex": escaped, "$options": "i"}},
            {"respondent.username": {"$regex": escaped, "$options": "i"}},
        ]
        if "$or" in query:
            query["$and"] = [{"$or": query.pop("$or")}, {"$or": keyword_query}]
        else:
            query["$or"] = keyword_query
    if has_attachments is not None:
        query["attachments.0"] = {"$exists": has_attachments}
    if username and username.strip():
        query["respondent.username"] = username.strip()
    if auth_type == "external":
        query["respondent.auth_type"] = "external"
    elif auth_type == "anonymous":
        query["respondent.auth_type"] = {"$ne": "external"}
    return query


def _summary(document: dict[str, Any], version: SurveyVersion | None = None) -> dict[str, Any]:
    payload = document.get("payload", {})
    respondent = document.get("respondent") or {"auth_type": "anonymous"}
    role_names = {role.id: role.label for role in version.roles} if version else {}
    page_names = {page.id: page.name for page in version.pages} if version else {}
    return {
        "id": str(document["_id"]),
        "submissionId": document.get("submission_id"),
        "surveyId": document.get("survey_id"),
        "surveyVersionId": document.get("survey_version_id"),
        "submittedAt": document.get("submitted_at"),
        "roles": payload.get("profile", {}).get("roleIds", []),
        "pages": payload.get("topPageIds", []),
        "roleNames": role_names,
        "pageNames": page_names,
        "attachmentCount": len(document.get("attachments", [])),
        "authType": respondent.get("auth_type", "anonymous"),
        "externalUserId": respondent.get("external_user_id"),
        "username": respondent.get("username"),
        "version": int(document.get("version", 1)),
        "revisionCount": len(document.get("revisions", [])),
        "updatedAt": document.get("updated_at"),
    }


async def _versions_for_documents(request: Request, documents: list[dict[str, Any]]) -> dict[str, SurveyVersion]:
    repository = get_repository(request)
    version_ids = list({
        version_id
        for document in documents
        if (version_id := document.get("survey_version_id")) is not None
    })
    version_documents = await repository.get_survey_versions(version_ids)
    return {
        str(document["_id"]): repository.survey_document(document)
        for document in version_documents
    }


@router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    enforce_same_origin(request)
    if not await asyncio.to_thread(verify_login, credentials, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(credentials.username, settings),
        max_age=settings.admin_session_hours * 3600,
        httponly=True,
        secure=settings.admin_secure_cookie,
        samesite="strict",
        path="/",
    )
    await get_repository(request).write_audit(credentials.username, "login")
    return {"username": credentials.username, "expiresIn": settings.admin_session_hours * 3600}


@router.post("/auth/logout")
async def logout(request: Request, response: Response, admin: AdminDependency) -> dict[str, str]:
    enforce_same_origin(request)
    response.delete_cookie(SESSION_COOKIE, path="/")
    await get_repository(request).write_audit(admin.username, "logout")
    return {"status": "ok"}


@router.get("/auth/session")
async def session(admin: AdminDependency) -> dict[str, str]:
    return {"username": admin.username}


@router.get("/submissions/stats")
async def submission_stats(request: Request, _: AdminDependency) -> dict[str, int]:
    return await get_repository(request).submission_stats()


@router.get("/submissions/catalog")
async def submission_catalog(request: Request, _: AdminDependency) -> dict[str, Any]:
    return await get_repository(request).submission_filter_catalog("dml-v4")


@router.get("/submissions")
async def submissions(
    request: Request,
    _: AdminDependency,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    version_id: str | None = Query(default=None, alias="version"),
    role: str | None = None,
    page: str | None = None,
    keyword: str | None = None,
    has_attachments: bool | None = Query(default=None, alias="hasAttachments"),
    username: str | None = Query(default=None, max_length=100),
    auth_type: str | None = Query(default=None, alias="authType", pattern="^(external|anonymous)$"),
) -> dict[str, Any]:
    query = _filters(date_from, date_to, version_id, role, page, keyword, has_attachments, username, auth_type)
    documents, next_cursor = await get_repository(request).list_submissions(query, cursor, limit)
    versions = await _versions_for_documents(request, documents)
    return {
        "items": [
            _json_value(_summary(item, versions.get(item.get("survey_version_id"))))
            for item in documents
        ],
        "nextCursor": next_cursor,
    }


def _csv_cell(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(_json_value(value), ensure_ascii=False)
    return f"'{text}" if text.lstrip().startswith(("=", "+", "-", "@")) else text


CSV_HEADERS = [
    "submission_id", "survey_id", "survey_version_id", "submitted_at", "auth_type",
    "external_user_id", "username", "roles",
    "role_context", "top_page_ids", "attachment_count", "top_page_reviews_json",
    "favorite_page_review_json", "other_page_reviews_json", "issue_evidence_json",
    "final_feedback",
]


def _csv_row(document: dict[str, Any]) -> list[str]:
    item = _summary(document)
    payload = document.get("payload", {})
    return [
        _csv_cell(item["submissionId"]),
        _csv_cell(item["surveyId"]),
        _csv_cell(item["surveyVersionId"]),
        _csv_cell(item["submittedAt"]),
        _csv_cell(item["authType"]),
        _csv_cell(item["externalUserId"] or ""),
        _csv_cell(item["username"] or ""),
        _csv_cell(item["roles"]),
        _csv_cell(payload.get("profile", {}).get("roleContext", "")),
        _csv_cell(item["pages"]),
        _csv_cell(item["attachmentCount"]),
        _csv_cell(payload.get("topPageReviews", [])),
        _csv_cell(payload.get("favoritePageReview", {})),
        _csv_cell(payload.get("otherPageReviews", [])),
        _csv_cell(payload.get("issueEvidence", {})),
        _csv_cell(payload.get("finalFeedback", "")),
    ]


@router.get("/submissions/export.csv")
async def export_submissions_csv(
    request: Request,
    admin: AdminDependency,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    version_id: str | None = Query(default=None, alias="version"),
    role: str | None = None,
    page: str | None = None,
    keyword: str | None = None,
    has_attachments: bool | None = Query(default=None, alias="hasAttachments"),
    username: str | None = Query(default=None, max_length=100),
    auth_type: str | None = Query(default=None, alias="authType", pattern="^(external|anonymous)$"),
) -> StreamingResponse:
    filters = _filters(date_from, date_to, version_id, role, page, keyword, has_attachments, username, auth_type)
    await get_repository(request).write_audit(admin.username, "export_csv", {"filters": _json_value(filters)})

    async def rows() -> AsyncIterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_HEADERS)
        yield "\ufeff" + buffer.getvalue()
        async for document in get_repository(request).list_all_submissions(filters):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(_csv_row(document))
            yield buffer.getvalue()

    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="survey-submissions.csv"'},
    )


async def _detail(request: Request, submission_id: str) -> tuple[dict[str, Any], SurveyVersion | None]:
    document = await get_repository(request).get_submission(submission_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交记录不存在")
    version = None
    if version_id := document.get("survey_version_id"):
        version_document = await get_repository(request).get_survey_version(version_id)
        if version_document:
            version = get_repository(request).survey_document(version_document)
    return document, version


@router.get("/submissions/{submission_id}")
async def submission_detail(request: Request, submission_id: str, _: AdminDependency) -> dict[str, Any]:
    document, version = await _detail(request, submission_id)
    payload = document.get("payload", {})
    attachments = []
    for item in document.get("attachments", []):
        attachments.append({
            "id": str(item["gridfs_id"]),
            "attachmentId": item["attachment_id"],
            "name": item["original_name"],
            "type": item["content_type"],
            "size": item["size"],
        })
    page_names = {page.id: page.name for page in version.pages} if version else {}
    sections = [
        {"id": "profile", "label": "角色与使用背景", "value": payload.get("profile", {})},
        {"id": "top-pages", "label": "重点页面评价", "value": payload.get("topPageReviews", []), "pageNames": page_names},
        {"id": "favorite", "label": "最高分页复盘", "value": payload.get("favoritePageReview", {})},
        {"id": "other-pages", "label": "其余页面评价", "value": payload.get("otherPageReviews", []), "pageNames": page_names},
        {"id": "issue-evidence", "label": "问题截图说明", "value": payload.get("issueEvidence", {}), "attachments": attachments},
        {"id": "final-feedback", "label": "遗漏反馈", "value": payload.get("finalFeedback", "")},
    ]
    return {
        **_json_value(_summary(document, version)),
        "sections": sections,
        "payload": _json_value(payload),
    }


@router.delete("/submissions/{submission_id}")
async def delete_submission(
    request: Request,
    submission_id: str,
    admin: AdminDependency,
) -> dict[str, str]:
    enforce_same_origin(request)
    document = await get_repository(request).delete_submission(submission_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交记录不存在")
    details = {
        "submissionId": document.get("submission_id", submission_id),
        "attachmentCount": len(document.get("attachments", [])),
    }
    try:
        await get_repository(request).write_audit(admin.username, "delete_submission", details)
    except Exception:
        logger.exception(
            "Submission deletion succeeded but its audit event could not be stored",
            extra={"submission_id": details["submissionId"]},
        )
    return {"status": "ok", "submissionId": str(details["submissionId"])}


@router.get("/submissions/{submission_id}/export.json")
async def export_submission_json(request: Request, submission_id: str, admin: AdminDependency) -> JSONResponse:
    document, _ = await _detail(request, submission_id)
    await get_repository(request).write_audit(admin.username, "export_json", {"submissionId": submission_id})
    headers = {"Content-Disposition": f'attachment; filename="{document["submission_id"]}.json"'}
    return JSONResponse(_json_value(document), headers=headers)


@router.get("/attachments/{attachment_id}")
async def attachment(request: Request, attachment_id: str, _: AdminDependency, download: bool = False) -> StreamingResponse:
    stream, document = await get_repository(request).open_attachment(attachment_id)
    if stream is None or document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    metadata = document.get("metadata", {})
    raw_name = str(metadata.get("original_name", "attachment"))
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name) or "attachment"
    disposition = "attachment" if download else "inline"

    async def chunks() -> AsyncIterator[bytes]:
        while chunk := await stream.read(256 * 1024):
            yield chunk

    return StreamingResponse(
        chunks(),
        media_type=metadata.get("content_type", "application/octet-stream"),
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/surveys/{survey_key}/draft", response_model=SurveyVersion)
async def get_draft(request: Request, survey_key: str, _: AdminDependency) -> SurveyVersion:
    document = await get_repository(request).get_survey_draft(survey_key)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问卷草稿不存在")
    return get_repository(request).survey_document(document)


@router.put("/surveys/{survey_key}/draft", response_model=SurveyVersion)
async def save_draft(
    request: Request,
    survey_key: str,
    update: SurveyDraftUpdate,
    admin: AdminDependency,
) -> SurveyVersion:
    enforce_same_origin(request)
    document = await get_repository(request).save_survey_draft(survey_key, update)
    if document is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿已被其他修改覆盖，请刷新后重试")
    await get_repository(request).write_audit(admin.username, "save_draft", {"surveyKey": survey_key})
    return get_repository(request).survey_document(document)


@router.post("/surveys/{survey_key}/publish", response_model=SurveyVersion)
async def publish(
    request: Request,
    survey_key: str,
    admin: AdminDependency,
    revision: int = Query(ge=1),
) -> SurveyVersion:
    enforce_same_origin(request)
    try:
        document = await get_repository(request).publish_survey_draft(survey_key, revision)
    except ValueError as error:
        code = status.HTTP_409_CONFLICT if "其他管理员" in str(error) else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=code, detail=str(error)) from error
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    if document is None:
        current = await get_repository(request).get_survey_draft(survey_key)
        if current is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿已被其他管理员修改，请刷新后重试")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问卷草稿不存在")
    try:
        await get_repository(request).write_audit(
            admin.username,
            "publish",
            {"surveyKey": survey_key, "version": document["version"]},
        )
    except Exception:
        logger.exception(
            "Survey publication succeeded but its audit event could not be stored",
            extra={"survey_key": survey_key, "version": document["version"]},
        )
    return get_repository(request).survey_document(document)


async def _set_closed(request: Request, survey_key: str, admin: AdminDependency, closed: bool) -> SurveyVersion:
    enforce_same_origin(request)
    document = await get_repository(request).set_survey_closed(survey_key, closed)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无已发布问卷")
    try:
        await get_repository(request).write_audit(
            admin.username,
            "close_survey" if closed else "reopen_survey",
            {"surveyKey": survey_key, "version": document.get("version")},
        )
    except Exception:
        logger.exception(
            "Survey close state changed but its audit event could not be stored",
            extra={"survey_key": survey_key, "closed": closed},
        )
    return get_repository(request).survey_document(document)


@router.post("/surveys/{survey_key}/close", response_model=SurveyVersion)
async def close_collection(request: Request, survey_key: str, admin: AdminDependency) -> SurveyVersion:
    return await _set_closed(request, survey_key, admin, True)


@router.post("/surveys/{survey_key}/reopen", response_model=SurveyVersion)
async def reopen_collection(request: Request, survey_key: str, admin: AdminDependency) -> SurveyVersion:
    return await _set_closed(request, survey_key, admin, False)


@router.get("/surveys/{survey_key}/versions", response_model=list[SurveyVersionSummary])
async def versions(request: Request, survey_key: str, _: AdminDependency) -> list[dict[str, Any]]:
    return await get_repository(request).list_survey_versions(survey_key)
