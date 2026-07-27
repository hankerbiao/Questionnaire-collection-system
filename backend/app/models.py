from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from app.api_model import ApiModel

MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
MAX_ATTACHMENTS = 3
ACCEPTED_ATTACHMENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


class AttachmentMeta(ApiModel):
    id: str = Field(min_length=1, max_length=128)
    question_id: Literal["issue-evidence"] = Field(alias="questionId")
    name: str = Field(min_length=1, max_length=500)
    type: str
    size: int = Field(ge=1, le=MAX_ATTACHMENT_SIZE)

    @model_validator(mode="after")
    def validate_type(self) -> "AttachmentMeta":
        if self.type not in ACCEPTED_ATTACHMENT_TYPES:
            raise ValueError("unsupported attachment type")
        return self


class Profile(ApiModel):
    role_ids: list[str] = Field(alias="roleIds", min_length=1, max_length=100)
    role_context: str = Field(alias="roleContext", min_length=100, max_length=1_000)

    @model_validator(mode="after")
    def validate_profile(self) -> "Profile":
        self.role_context = self.role_context.strip()
        if len(self.role_context) < 100:
            raise ValueError("roleContext must contain at least 100 characters after trimming")
        if len(self.role_ids) != len(set(self.role_ids)):
            raise ValueError("roleIds must be unique")
        return self


class PageReview(ApiModel):
    page_id: str = Field(alias="pageId", min_length=1, max_length=128)
    overall_score: int = Field(alias="overallScore", ge=1, le=10)
    feature_scores: dict[str, int] = Field(alias="featureScores", min_length=1, max_length=100)
    strengths: str = Field(min_length=1, max_length=2_000)
    pain_points: str = Field(alias="painPoints", min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def trim_required_text(self) -> "PageReview":
        self.strengths = self.strengths.strip()
        self.pain_points = self.pain_points.strip()
        if not self.strengths or not self.pain_points:
            raise ValueError("strengths and painPoints may not be blank")
        if any(score < 1 or score > 10 for score in self.feature_scores.values()):
            raise ValueError("feature scores must be between 1 and 10")
        return self


class FavoritePageReview(ApiModel):
    page_id: str = Field(alias="pageId", min_length=1, max_length=128)
    winning_reason: str = Field(alias="winningReason", min_length=1, max_length=2_000)
    improvement: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def trim_required_text(self) -> "FavoritePageReview":
        self.winning_reason = self.winning_reason.strip()
        self.improvement = self.improvement.strip()
        if not self.winning_reason or not self.improvement:
            raise ValueError("favorite page review text may not be blank")
        return self


class OtherPageReview(ApiModel):
    page_id: str = Field(alias="pageId", min_length=1, max_length=128)
    status: Literal["unused", "rated"] = "unused"
    overall_score: int | None = Field(default=None, alias="overallScore", ge=1, le=10)
    strengths: str = Field(default="", max_length=2_000)
    pain_points: str = Field(default="", alias="painPoints", max_length=2_000)

    @model_validator(mode="after")
    def validate_status(self) -> "OtherPageReview":
        self.strengths = self.strengths.strip()
        self.pain_points = self.pain_points.strip()
        if self.status == "rated" and self.overall_score is None:
            raise ValueError("rated pages require overallScore")
        if self.status == "unused" and self.overall_score is not None:
            raise ValueError("unused pages may not include overallScore")
        return self


class IssueEvidence(ApiModel):
    description: str = Field(default="", max_length=2_000)
    attachments: list[AttachmentMeta] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)

    @model_validator(mode="after")
    def validate_description(self) -> "IssueEvidence":
        self.description = self.description.strip()
        if self.attachments and not self.description:
            raise ValueError("上传截图后必须填写问题说明")
        ids = [attachment.id for attachment in self.attachments]
        if len(ids) != len(set(ids)):
            raise ValueError("attachment IDs must be unique")
        return self


class SurveySubmission(ApiModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    survey_version_id: str = Field(alias="surveyVersionId", min_length=1)
    survey_id: str = Field(alias="surveyId", min_length=1, max_length=128)
    started_at: datetime = Field(alias="startedAt")
    submitted_at: datetime = Field(alias="submittedAt")
    profile: Profile
    top_page_ids: list[str] = Field(alias="topPageIds", min_length=3, max_length=3)
    top_page_reviews: list[PageReview] = Field(alias="topPageReviews", min_length=3, max_length=3)
    favorite_page_review: FavoritePageReview = Field(alias="favoritePageReview")
    other_page_reviews: list[OtherPageReview] = Field(alias="otherPageReviews", max_length=300)
    issue_evidence: IssueEvidence = Field(alias="issueEvidence")
    final_feedback: str = Field(default="", alias="finalFeedback", max_length=2_000)

    @model_validator(mode="after")
    def validate_shape(self) -> "SurveySubmission":
        self.final_feedback = self.final_feedback.strip()
        if len(self.top_page_ids) != len(set(self.top_page_ids)):
            raise ValueError("topPageIds must be unique")
        review_ids = [review.page_id for review in self.top_page_reviews]
        if review_ids != self.top_page_ids:
            raise ValueError("topPageReviews must follow topPageIds order")
        other_ids = [review.page_id for review in self.other_page_reviews]
        if len(other_ids) != len(set(other_ids)) or set(other_ids) & set(self.top_page_ids):
            raise ValueError("other page reviews must be unique and separate from top pages")
        if self.started_at.tzinfo is None or self.submitted_at.tzinfo is None:
            raise ValueError("submission timestamps must include a timezone")
        if self.started_at > self.submitted_at:
            raise ValueError("startedAt must not be after submittedAt")
        if self.submitted_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("submittedAt is too far in the future")
        return self

    def attachment_map(self) -> dict[str, AttachmentMeta]:
        return {attachment.id: attachment for attachment in self.issue_evidence.attachments}


class SubmissionResponse(ApiModel):
    submission_id: str = Field(alias="submissionId")
