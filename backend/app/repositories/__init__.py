from app.repositories.attachments import AttachmentRepositoryMixin
from app.repositories.base import RepositoryBase
from app.repositories.submissions import SubmissionRepositoryMixin
from app.repositories.surveys import SurveyRepositoryMixin


class SubmissionRepository(
    AttachmentRepositoryMixin,
    SurveyRepositoryMixin,
    SubmissionRepositoryMixin,
    RepositoryBase,
):
    pass


__all__ = ["SubmissionRepository"]
