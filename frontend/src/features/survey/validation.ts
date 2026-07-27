import type { PageDefinition, PageReview, SurveyDraft } from '../../types'

function pageReviewError(page: PageDefinition, review?: PageReview) {
  if (!review?.overallScore) return `请为“${page.name}”填写综合体验评分。`
  const featureIds = page.features.filter((feature) => feature.enabled).map((feature) => feature.id)
  if (featureIds.some((id) => !review.featureScores[id])) return `请完成“${page.name}”的全部功能点评分。`
  if (!review.strengths.trim()) return `请填写“${page.name}”的优点。`
  if (!review.painPoints.trim()) return `请填写“${page.name}”的槽点。`
  return ''
}

export function validateSurveyStep(step: number, draft: SurveyDraft, enabledPages: PageDefinition[], topPages: PageDefinition[]): string {
  if (step === 0) {
    if (!draft.roleIds.length) return '请至少选择一个角色。'
    if (draft.roleContext.trim().length < 100) return '“其他 / 补充说明”去除首尾空白后至少需要 100 字。'
  }
  if (step === 1 && draft.topPageIds.length !== 3) return '请选择恰好 3 个最常用的页面。'
  if (step >= 2 && step <= 4) {
    const page = topPages[step - 2]
    if (!page) return '重点页面信息不完整，请返回重新选择。'
    return pageReviewError(page, draft.topPageReviews[step - 2])
  }
  if (step === 5) {
    if (!draft.favoritePageReview.pageId) return '综合分并列，请从并列页面中选择一个。'
    if (!draft.favoritePageReview.winningReason.trim()) return '请填写这个页面胜出的原因。'
    if (!draft.favoritePageReview.improvement.trim()) return '请填写这个页面仍需改善之处。'
  }
  if (step === 6) {
    const expected = enabledPages.filter((page) => !draft.topPageIds.includes(page.id))
    if (draft.otherPageReviews.length !== expected.length) return '其余页面列表不完整，请刷新后重试。'
    if (draft.otherPageReviews.some((review) => review.status === 'rated' && !review.overallScore)) return '选择“使用过”的页面必须填写综合评分。'
  }
  if (step === 7 && draft.attachments.length > 0 && !draft.issueDescription.trim()) return '上传截图后，请填写问题说明。'
  return ''
}
