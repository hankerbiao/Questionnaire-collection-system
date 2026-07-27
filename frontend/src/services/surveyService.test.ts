import { expect, it, vi } from 'vitest'
import type { AttachmentRecord, SurveyDraft } from '../types'
import { buildSubmission, HttpSurveyService } from './surveyService'

const draft = (): SurveyDraft => ({
  schemaVersion: 1, id: 'survey-id', surveyVersionId: 'version-id', createdAt: '2026-07-24T01:00:00Z', updatedAt: '2026-07-24T01:00:00Z', currentStep: 9,
  roleIds: ['tester'], roleContext: 'x'.repeat(100), topPageIds: ['a', 'b', 'c'],
  topPageReviews: ['a', 'b', 'c'].map((pageId, index) => ({ pageId, overallScore: 8 - index, featureScores: { [`f-${pageId}`]: 7 }, strengths: ' 优点 ', painPoints: ' 槽点 ' })),
  favoritePageReview: { pageId: 'a', winningReason: ' 原因 ', improvement: ' 改进 ' },
  otherPageReviews: [{ pageId: 'd', status: 'unused', strengths: '', painPoints: '' }], issueDescription: '', attachments: [], finalFeedback: '',
})

it('builds the explicit submission shape', () => {
  const payload = buildSubmission(draft())
  expect(payload.profile.roleIds).toEqual(['tester'])
  expect(payload.topPageReviews[0].strengths).toBe('优点')
  expect(payload.favoritePageReview.winningReason).toBe('原因')
  expect(payload.issueEvidence.attachments).toEqual([])
})

it('submits screenshots using attachment IDs as filenames', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ submissionId: 'DML-TEST' }), { status: 201 })))
  const value = draft()
  value.attachments = [{ id: 'file-1', questionId: 'issue-evidence', name: 'screen.png', type: 'image/png', size: 3 }]
  value.issueDescription = '问题说明'
  const record: AttachmentRecord = { ...value.attachments[0], dataUrl: 'data:image/png;base64,AQID' }
  await expect(new HttpSurveyService('/api/v1').submit(buildSubmission(value), [record])).resolves.toEqual({ submissionId: 'DML-TEST' })
  const body = vi.mocked(fetch).mock.calls[0][1]?.body as FormData
  expect((body.get('files') as File).name).toBe('file-1')
})
