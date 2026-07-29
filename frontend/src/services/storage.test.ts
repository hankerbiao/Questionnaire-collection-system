import { describe, expect, it } from 'vitest'
import type { AttachmentRecord, SurveyDraft } from '../types'
import { attachmentRecordsForDraft, DRAFT_STORAGE_KEY, loadDraft, ownerKeyForUser, saveDraft, validateAttachmentFiles } from './storage'

const draft = (): SurveyDraft => ({
  schemaVersion: 1, id: 'id', surveyVersionId: 'v1', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
  currentStep: 3, roleIds: [], roleContext: '', topPageIds: [], topPageReviews: [],
  favoritePageReview: { pageId: '', winningReason: '', improvement: '' }, otherPageReviews: [],
  issueDescription: '', attachments: [], finalFeedback: '',
})

describe('new draft storage', () => {
  it('restores only schema version 1', () => {
    saveDraft(draft())
    expect(loadDraft()?.currentStep).toBe(3)
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ ...draft(), schemaVersion: 0 }))
    expect(loadDraft()).toBeNull()
  })

  it('isolates drafts by external user ID', () => {
    const userA = ownerKeyForUser('user-a')
    const userB = ownerKeyForUser('user-b')
    saveDraft({ ...draft(), roleContext: 'user a' }, userA)
    saveDraft({ ...draft(), roleContext: 'user b' }, userB)
    expect(loadDraft(userA)?.roleContext).toBe('user a')
    expect(loadDraft(userB)?.roleContext).toBe('user b')
    expect(loadDraft()?.roleContext).not.toBe('user a')
  })

  it('validates screenshot count, type and size', () => {
    const image = new File(['x'], 'screen.png', { type: 'image/png' })
    const text = new File(['x'], 'note.txt', { type: 'text/plain' })
    const large = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.webp', { type: 'image/webp' })
    expect(validateAttachmentFiles([image, image], 2)).toContain('最多上传 3 张')
    expect(validateAttachmentFiles([text], 0)).toContain('仅支持')
    expect(validateAttachmentFiles([large], 0)).toContain('超过 5 MB')
  })

  it('keeps only attachment records referenced by the active draft', () => {
    const record = (id: string): AttachmentRecord => ({
      id, questionId: 'issue-evidence', name: `${id}.png`, type: 'image/png', size: 1, dataUrl: `data:${id}`,
    })

    expect(attachmentRecordsForDraft([record('active'), record('orphan')], new Set(['active'])))
      .toEqual([record('active')])
  })
})
