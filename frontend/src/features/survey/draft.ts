import type { OtherPageReview, PageReview, PublishedSurvey, SurveyDraft, SurveySubmission } from '../../types'
import { createId } from '../../utils/id'

const ROLE_CONTEXT_TEMPLATE = `1. 我负责哪些项目和团队：

2. 我通常如何完成任务：

3. 我在 DML 中的典型工作流程：

4. 我希望 DML 帮助解决的问题：`

export const emptyPageReview = (pageId: string): PageReview => ({
  pageId,
  featureScores: {},
  strengths: '',
  painPoints: '',
})

export const emptyOtherReview = (pageId: string): OtherPageReview => ({
  pageId,
  status: 'unused',
  strengths: '',
  painPoints: '',
})

export function createDraft(versionId: string): SurveyDraft {
  const now = new Date().toISOString()
  return {
    schemaVersion: 1,
    id: createId(),
    surveyVersionId: versionId,
    createdAt: now,
    updatedAt: now,
    currentStep: 0,
    roleIds: [],
    roleContext: ROLE_CONTEXT_TEMPLATE,
    topPageIds: [],
    topPageReviews: [],
    favoritePageReview: { pageId: '', winningReason: '', improvement: '' },
    otherPageReviews: [],
    issueDescription: '',
    attachments: [],
    finalFeedback: '',
  }
}

export function reconcileDraft(draft: SurveyDraft, survey: PublishedSurvey): SurveyDraft {
  if (draft.surveyVersionId !== survey.versionId) return createDraft(survey.versionId)
  const pageIds = new Set(survey.pages.filter((page) => page.enabled).map((page) => page.id))
  const topPageIds = draft.topPageIds.filter((id) => pageIds.has(id)).slice(0, 3)
  const topReviews = new Map(draft.topPageReviews.map((review) => [review.pageId, review]))
  const otherReviews = new Map(draft.otherPageReviews.map((review) => [review.pageId, review]))
  return {
    ...draft,
    roleContext: draft.roleContext || ROLE_CONTEXT_TEMPLATE,
    topPageIds,
    topPageReviews: topPageIds.map((pageId) => topReviews.get(pageId) ?? emptyPageReview(pageId)),
    otherPageReviews: survey.pages
      .filter((page) => page.enabled && !topPageIds.includes(page.id))
      .map((page) => otherReviews.get(page.id) ?? emptyOtherReview(page.id)),
  }
}

export const selectFavoritePage = (review: SurveyDraft['favoritePageReview'], pageId: string) => (
  review.pageId === pageId ? review : { pageId, winningReason: '', improvement: '' }
)

export function draftFromSubmission(payload: SurveySubmission): SurveyDraft {
  return {
    schemaVersion: 1,
    id: payload.surveyId,
    surveyVersionId: payload.surveyVersionId,
    createdAt: payload.startedAt,
    updatedAt: new Date().toISOString(),
    currentStep: 0,
    roleIds: payload.profile.roleIds,
    roleContext: payload.profile.roleContext,
    topPageIds: payload.topPageIds,
    topPageReviews: payload.topPageReviews.map((review) => ({
      pageId: review.pageId,
      overallScore: review.overallScore,
      featureScores: review.featureScores,
      strengths: review.strengths,
      painPoints: review.painPoints,
    })),
    favoritePageReview: payload.favoritePageReview,
    otherPageReviews: payload.otherPageReviews,
    issueDescription: payload.issueEvidence.description,
    attachments: payload.issueEvidence.attachments,
    finalFeedback: payload.finalFeedback,
  }
}
