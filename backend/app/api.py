import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.models import SubmissionResponse, SurveySubmission
from app.default_survey import default_survey
from app.repository import SubmissionRepository
from app.services import SubmissionError, SubmissionService
from app.survey_models import SurveyVersion
from app.user_auth import UserDependency, respondent_document
from app.auth import enforce_same_origin

router = APIRouter(prefix="/api/v1")
MAX_PAYLOAD_SIZE = 1024 * 1024


def get_repository(request: Request) -> SubmissionRepository:
    return request.app.state.repository


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    try:
        repository = get_repository(request)
        await repository.ping()
        await repository.ensure_indexes()
        await repository.ensure_default_survey(
            default_survey("published", 1),
            default_survey("draft", 0),
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂时不可用",
        ) from error
    return {"status": "ok"}


@router.get("/surveys/current", response_model=SurveyVersion)
async def current_survey(request: Request) -> SurveyVersion:
    document = await get_repository(request).get_current_survey()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无已发布问卷")
    return get_repository(request).survey_document(document)


@router.get("/surveys/versions/{version_id}", response_model=SurveyVersion)
async def survey_version(request: Request, version_id: str) -> SurveyVersion:
    document = await get_repository(request).get_survey_version(version_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问卷版本不存在")
    return get_repository(request).survey_document(document)


@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_submission(
    request: Request,
    payload: Annotated[str, Form()],
    user: UserDependency,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> SubmissionResponse:
    if user is not None:
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
        submission_id = await SubmissionService(get_repository(request)).submit(
            parsed_payload,
            files or [],
            respondent_document(user),
        )
    except SubmissionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂时不可用",
        ) from error

    return SubmissionResponse(submission_id=submission_id)
