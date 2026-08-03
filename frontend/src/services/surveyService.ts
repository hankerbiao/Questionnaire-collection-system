import { API_BASE } from '../shared/apiConfig'
import type { AttachmentRecord, SurveyDraft, SurveySubmission } from '../types'

function dataUrlToBlob(record: AttachmentRecord): Blob {
  const [, body = ''] = record.dataUrl.split(',', 2)
  const decoded = atob(body)
  const bytes = Uint8Array.from(decoded, (character) => character.charCodeAt(0))
  return new Blob([bytes], { type: record.type })
}

export function buildSubmission(draft: SurveyDraft): SurveySubmission {
  return {
    schemaVersion: 1,
    surveyId: draft.id,
    surveyVersionId: draft.surveyVersionId,
    startedAt: draft.createdAt,
    submittedAt: new Date().toISOString(),
    profile: { roleIds: draft.roleIds, roleContext: draft.roleContext.trim() },
    topPageIds: draft.topPageIds,
    topPageReviews: draft.topPageReviews.map((review) => ({
      ...review,
      overallScore: review.overallScore!,
      strengths: review.strengths.trim(),
      painPoints: review.painPoints.trim(),
    })),
    favoritePageReview: {
      ...draft.favoritePageReview,
      winningReason: draft.favoritePageReview.winningReason.trim(),
      improvement: draft.favoritePageReview.improvement.trim(),
    },
    otherPageReviews: draft.otherPageReviews.map((review) => ({
      ...review,
      strengths: review.strengths.trim(),
      painPoints: review.painPoints.trim(),
    })),
    issueEvidence: { description: draft.issueDescription.trim(), attachments: draft.attachments },
    finalFeedback: draft.finalFeedback.trim(),
  }
}

export class HttpSurveyService {
  constructor(private readonly base = API_BASE) {}

  async submit(payload: SurveySubmission, attachments: AttachmentRecord[]) {
    const expected = new Set(payload.issueEvidence.attachments.map((item) => item.id))
    const records = new Map(attachments.map((item) => [item.id, item]))
    if ([...expected].some((id) => !records.has(id))) throw new Error('部分截图无法读取，请重新上传。')
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    for (const id of expected) {
      const record = records.get(id)!
      form.append('files', dataUrlToBlob(record), record.id)
    }
    const response = await fetch(`${this.base.replace(/\/$/, '')}/submissions`, { method: 'POST', body: form })
    const body = await response.json().catch(() => null) as { submissionId?: string; detail?: unknown } | null
    if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `提交失败（HTTP ${response.status}）`)
    if (!body?.submissionId) throw new Error('服务器未返回有效提交编号')
    return { submissionId: body.submissionId }
  }

  async edit(submissionId: string, payload: SurveySubmission, attachments: AttachmentRecord[], expectedVersion: number) {
    const records = new Map(attachments.map((item) => [item.id, item]))
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    form.append('expected_version', String(expectedVersion))
    for (const meta of payload.issueEvidence.attachments) {
      const record = records.get(meta.id)
      if (record) form.append('files', dataUrlToBlob(record), record.id)
    }
    const response = await fetch(`${this.base.replace(/\/$/, '')}/submissions/${encodeURIComponent(submissionId)}`, { method: 'PUT', body: form })
    const body = await response.json().catch(() => null) as { submissionId?: string; version?: number; detail?: unknown } | null
    if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `保存失败（HTTP ${response.status}）`)
    if (!body?.submissionId) throw new Error('服务器未返回有效提交编号')
    return { submissionId: body.submissionId, version: body.version ?? expectedVersion }
  }
}

export const surveyService = new HttpSurveyService()
