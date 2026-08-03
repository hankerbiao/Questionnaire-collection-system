import { API_BASE } from '../shared/apiConfig'
import type { SubmissionDetail, SubmissionFilterCatalog, SubmissionRow, SurveyVersionConfig } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json', ...init.headers } : init?.headers,
  })
  if (response.status === 401) throw new Error('UNAUTHORIZED')
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `请求失败（${response.status}）`)
  return body as T
}

export const adminApi = {
  session: () => request<{ username: string }>('/admin/auth/session'),
  login: (username: string, password: string) => request<{ username: string }>('/admin/auth/login', {
    method: 'POST', body: JSON.stringify({ username, password }),
  }),
  logout: () => request('/admin/auth/logout', { method: 'POST', body: '{}' }),
  stats: () => request<{ total: number; last7Days: number; withAttachments: number }>('/admin/submissions/stats'),
  submissionCatalog: () => request<SubmissionFilterCatalog>('/admin/submissions/catalog'),
  submissions: (params: URLSearchParams) => request<{ items: SubmissionRow[]; nextCursor?: string }>(`/admin/submissions?${params}`),
  detail: (id: string) => request<SubmissionDetail>(`/admin/submissions/${id}`),
  deleteSubmission: (id: string) => request<{ status: string; submissionId: string }>(`/admin/submissions/${id}`, { method: 'DELETE' }),
  draft: () => request<SurveyVersionConfig>('/admin/surveys/dml-v4/draft'),
  saveDraft: (draft: SurveyVersionConfig) => request<SurveyVersionConfig>('/admin/surveys/dml-v4/draft', {
    method: 'PUT',
    body: JSON.stringify({
      revision: draft.revision, title: draft.title, description: draft.description,
      roles: draft.roles, pages: draft.pages,
    }),
  }),
  publish: (revision: number) => request<SurveyVersionConfig>(`/admin/surveys/dml-v4/publish?revision=${revision}`, { method: 'POST', body: '{}' }),
  closeCollection: () => request<SurveyVersionConfig>('/admin/surveys/dml-v4/close', { method: 'POST', body: '{}' }),
  reopenCollection: () => request<SurveyVersionConfig>('/admin/surveys/dml-v4/reopen', { method: 'POST', body: '{}' }),
  versions: () => request<Array<{ versionId: string; version: number; status: string; publishedAt: string | null; closedAt: string | null; submissionCount: number }>>('/admin/surveys/dml-v4/versions'),
  exportUrl: (params: URLSearchParams) => `${API_BASE}/admin/submissions/export.csv?${params}`,
  attachmentUrl: (id: string, download = false) => `${API_BASE}/admin/attachments/${id}${download ? '?download=true' : ''}`,
  jsonUrl: (id: string) => `${API_BASE}/admin/submissions/${id}/export.json`,
}
