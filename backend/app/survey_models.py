from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.api_model import ApiModel


class SurveyRole(ApiModel):
    id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1_000)


class PageFeatureDefinition(ApiModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1_000)
    order: int = Field(ge=0)
    enabled: bool = True


class PageDefinition(ApiModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=100)
    order: int = Field(ge=0)
    enabled: bool = True
    features: list[PageFeatureDefinition] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_features(self) -> "PageDefinition":
        feature_ids = [feature.id for feature in self.features]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError(f"page {self.id} contains duplicate feature IDs")
        return self


class SurveyVersion(ApiModel):
    version_id: str | None = Field(default=None, alias="versionId")
    survey_key: str = Field(alias="surveyKey", min_length=1, max_length=100)
    version: int = Field(ge=0)
    status: Literal["draft", "published", "archived"]
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2_000)
    roles: list[SurveyRole] = Field(min_length=1, max_length=100)
    pages: list[PageDefinition] = Field(min_length=1, max_length=300)
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    published_at: datetime | None = Field(default=None, alias="publishedAt")

    @model_validator(mode="after")
    def validate_structure(self) -> "SurveyVersion":
        role_ids = [role.id for role in self.roles]
        page_ids = [page.id for page in self.pages]
        feature_ids = [feature.id for page in self.pages for feature in page.features]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("role IDs must be unique")
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("page IDs must be unique")
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("feature IDs must be globally unique")
        return self

    def validate_for_publish(self) -> None:
        enabled_pages = [page for page in self.pages if page.enabled]
        if len(enabled_pages) < 3:
            raise ValueError("发布问卷至少需要 3 个启用页面")
        empty_pages = [page.name for page in enabled_pages if not any(feature.enabled for feature in page.features)]
        if empty_pages:
            raise ValueError(f"以下启用页面至少需要一个启用功能点：{'、'.join(empty_pages)}")


class SurveyDraftUpdate(ApiModel):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2_000)
    roles: list[SurveyRole] = Field(min_length=1, max_length=100)
    pages: list[PageDefinition] = Field(min_length=1, max_length=300)


class SurveyVersionSummary(ApiModel):
    version_id: str = Field(alias="versionId")
    version: int
    status: str
    published_at: datetime | None = Field(alias="publishedAt")
    submission_count: int = Field(alias="submissionCount")
