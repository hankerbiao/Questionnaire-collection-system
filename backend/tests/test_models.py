from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.default_survey import default_survey
from app.models import SurveySubmission

VERSION_ID = "507f1f77bcf86cd799439011"


def submission_data() -> dict:
    survey = default_survey("published", 1)
    pages = [page for page in survey.pages if page.enabled]
    top = pages[:3]
    return {
        "schemaVersion": 1,
        "surveyVersionId": VERSION_ID,
        "surveyId": "survey-1",
        "startedAt": "2026-07-24T01:00:00Z",
        "submittedAt": "2026-07-24T02:00:00Z",
        "profile": {"roleIds": ["tester"], "roleContext": "x" * 100},
        "topPageIds": [page.id for page in top],
        "topPageReviews": [
            {
                "pageId": page.id,
                "overallScore": 9 - index,
                "featureScores": {feature.id: 8 for feature in page.features if feature.enabled},
                "strengths": "优点",
                "painPoints": "槽点",
            }
            for index, page in enumerate(top)
        ],
        "favoritePageReview": {
            "pageId": top[0].id,
            "winningReason": "胜出原因",
            "improvement": "仍需改善",
        },
        "otherPageReviews": [
            {"pageId": page.id, "status": "unused", "strengths": "", "painPoints": ""}
            for page in pages[3:]
        ],
        "issueEvidence": {"description": "", "attachments": []},
        "finalFeedback": "",
    }


def attachment(attachment_id: str) -> dict:
    return {
        "id": attachment_id,
        "questionId": "issue-evidence",
        "name": f"{attachment_id}.png",
        "type": "image/png",
        "size": 68,
    }


def test_accepts_new_frontend_payload_shape() -> None:
    payload = SurveySubmission.model_validate(submission_data())
    assert payload.profile.role_context == "x" * 100
    assert payload.model_dump(by_alias=True, mode="json")["topPageIds"] == payload.top_page_ids


def test_role_context_uses_trimmed_100_character_boundary() -> None:
    data = submission_data()
    data["profile"]["roleContext"] = " " + "x" * 99 + " "
    with pytest.raises(ValidationError, match="at least 100"):
        SurveySubmission.model_validate(data)
    data["profile"]["roleContext"] = " " + "x" * 100 + " "
    assert len(SurveySubmission.model_validate(data).profile.role_context) == 100


def test_rejects_invalid_score_and_duplicate_top_pages() -> None:
    data = submission_data()
    data["topPageReviews"][0]["overallScore"] = 11
    with pytest.raises(ValidationError):
        SurveySubmission.model_validate(data)
    data = submission_data()
    data["topPageIds"][1] = data["topPageIds"][0]
    with pytest.raises(ValidationError, match="unique"):
        SurveySubmission.model_validate(data)


def test_other_page_status_controls_score() -> None:
    data = submission_data()
    data["otherPageReviews"][0].update({"status": "rated", "overallScore": None})
    with pytest.raises(ValidationError, match="require overallScore"):
        SurveySubmission.model_validate(data)


def test_screenshot_requires_description_and_supported_type() -> None:
    data = deepcopy(submission_data())
    data["issueEvidence"]["attachments"] = [attachment("screen")]
    with pytest.raises(ValidationError, match="必须填写问题说明"):
        SurveySubmission.model_validate(data)
    data["issueEvidence"]["description"] = "问题说明"
    data["issueEvidence"]["attachments"][0]["type"] = "text/plain"
    with pytest.raises(ValidationError, match="unsupported"):
        SurveySubmission.model_validate(data)
