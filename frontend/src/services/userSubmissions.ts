import { API_BASE } from '../shared/apiConfig'
import type { MySubmissionDetail, MySubmissionRow } from '../types'

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include' })
  if (response.status === 401) throw new Error('登录已过期，请重新登录后查看。')
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `请求失败（${response.status}）`)
  return body as T
}

export const getMySubmissions = (cursor?: string) => request<{ items: MySubmissionRow[]; nextCursor?: string }>(
  `/submissions/mine${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`,
)

export const getMySubmission = (id: string) => request<MySubmissionDetail>(`/submissions/${encodeURIComponent(id)}`)

export const myAttachmentUrl = (submissionId: string, gridfsId: string) =>
  `${API_BASE}/submissions/${encodeURIComponent(submissionId)}/attachments/${encodeURIComponent(gridfsId)}`
