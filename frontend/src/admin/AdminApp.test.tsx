import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import AdminApp from './AdminApp'
import { adminApi } from './api'
import type { SubmissionDetail, SubmissionRow, SurveyVersionConfig } from './types'

vi.mock('./api', () => ({ adminApi: {
  session: vi.fn(), draft: vi.fn(), stats: vi.fn(), submissionCatalog: vi.fn(),
  submissions: vi.fn(), detail: vi.fn(), deleteSubmission: vi.fn(), saveDraft: vi.fn(), publish: vi.fn(),
  exportUrl: vi.fn(() => '#'), jsonUrl: vi.fn(() => '#'), attachmentUrl: vi.fn(() => '#'),
} }))

const draft: SurveyVersionConfig = {
  versionId: 'draft-1', surveyKey: 'dml-v4', version: 0, status: 'draft', revision: 1,
  title: 'DML 使用体验调研', description: '', roles: [{ id: 'tester', label: '测试人员', description: '' }],
  pages: [{ id: 'requirements', name: '测试需求', category: '需求与用例', order: 1, enabled: true, features: [{ id: 'requirements-search', name: '搜索', description: '', order: 1, enabled: true }] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  history.replaceState({}, '', '/admin/surveys')
  vi.mocked(adminApi.session).mockResolvedValue({ username: 'admin' })
  vi.mocked(adminApi.draft).mockResolvedValue(draft)
  vi.mocked(adminApi.stats).mockResolvedValue({ total: 0, last7Days: 0, withAttachments: 0 })
  vi.mocked(adminApi.submissionCatalog).mockResolvedValue({ roles: [], pages: [] })
  vi.mocked(adminApi.submissions).mockResolvedValue({ items: [] })
})

it('edits the page and feature catalog', async () => {
  const user = userEvent.setup()
  render(<AdminApp />)
  expect(await screen.findByText('页面目录')).toBeInTheDocument()
  expect(screen.getByDisplayValue('测试需求')).toBeInTheDocument()
  expect(screen.getByDisplayValue('搜索')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /添加功能点/ }))
  expect(screen.getByDisplayValue('新功能点')).toBeInTheDocument()
})

it('keeps the newest submission filter response when requests finish out of order', async () => {
  const user = userEvent.setup()
  history.replaceState({}, '', '/admin/results')
  vi.mocked(adminApi.stats).mockResolvedValue({ total: 2, last7Days: 2, withAttachments: 0 })
  vi.mocked(adminApi.submissionCatalog).mockResolvedValue({
    roles: [{ id: 'tester', label: '测试人员' }], pages: [],
  })
  let resolveFirst!: (value: { items: SubmissionRow[] }) => void
  let resolveSecond!: (value: { items: SubmissionRow[] }) => void
  vi.mocked(adminApi.submissions)
    .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
    .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve }))
  const row = (id: string): SubmissionRow => ({
    id, submissionId: id, surveyId: `survey-${id}`, surveyVersionId: 'version-1',
    submittedAt: new Date().toISOString(), roles: ['tester'], pages: [],
    roleNames: { tester: '测试人员' }, pageNames: {}, attachmentCount: 0,
  })

  render(<AdminApp />)
  await screen.findByRole('option', { name: '测试人员' })
  await user.selectOptions(screen.getByRole('combobox', { name: '角色筛选' }), 'tester')
  expect(adminApi.submissions).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: /筛选/ }))
  await waitFor(() => expect(adminApi.submissions).toHaveBeenCalledTimes(2))
  resolveSecond({ items: [row('new-result')] })
  expect(await screen.findByText('new-result')).toBeInTheDocument()
  resolveFirst({ items: [row('old-result')] })
  await waitFor(() => expect(screen.queryByText('old-result')).not.toBeInTheDocument())
  expect(screen.getByText('new-result')).toBeInTheDocument()
})

it('deletes a submission from its detail drawer and refreshes results', async () => {
  const user = userEvent.setup()
  history.replaceState({}, '', '/admin/results')
  const row: SubmissionRow = {
    id: 'row-1', submissionId: 'DML-DELETE-1', surveyId: 'survey-1', surveyVersionId: 'version-1',
    submittedAt: new Date().toISOString(), roles: ['tester'], pages: [],
    roleNames: { tester: '测试人员' }, pageNames: {}, attachmentCount: 1,
  }
  const detail: SubmissionDetail = { ...row, sections: [], payload: {} }
  vi.mocked(adminApi.submissions)
    .mockResolvedValueOnce({ items: [row] })
    .mockResolvedValue({ items: [] })
  vi.mocked(adminApi.detail).mockResolvedValue(detail)
  vi.mocked(adminApi.deleteSubmission).mockResolvedValue({ status: 'ok', submissionId: row.submissionId })
  vi.mocked(adminApi.stats)
    .mockResolvedValueOnce({ total: 1, last7Days: 1, withAttachments: 1 })
    .mockResolvedValue({ total: 0, last7Days: 0, withAttachments: 0 })
  vi.spyOn(window, 'confirm').mockReturnValue(true)

  render(<AdminApp />)
  await user.click(await screen.findByText(row.submissionId))
  await user.click(await screen.findByRole('button', { name: '删除问卷' }))

  await waitFor(() => expect(adminApi.deleteSubmission).toHaveBeenCalledWith(row.id))
  await waitFor(() => expect(screen.queryByText(row.submissionId)).not.toBeInTheDocument())
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('关联截图也会一并删除'))
  expect(adminApi.stats).toHaveBeenCalledTimes(2)
})

it('disables catalog editing while a save is in flight', async () => {
  const user = userEvent.setup()
  let resolveSave!: (value: SurveyVersionConfig) => void
  vi.mocked(adminApi.saveDraft).mockReturnValue(new Promise((resolve) => { resolveSave = resolve }))
  render(<AdminApp />)
  const title = await screen.findByDisplayValue('DML 使用体验调研')
  await user.clear(title)
  await user.type(title, '新版问卷')
  await user.click(screen.getByRole('button', { name: /保存草稿/ }))
  expect(title).toBeDisabled()
  resolveSave({ ...draft, title: '新版问卷', revision: 2 })
  await waitFor(() => expect(title).not.toBeDisabled())
})

it('follows browser history between admin views', async () => {
  history.replaceState({}, '', '/admin/surveys')
  render(<AdminApp />)
  expect(await screen.findByText('页面目录')).toBeInTheDocument()

  history.pushState({}, '', '/admin/results')
  window.dispatchEvent(new PopStateEvent('popstate'))

  expect(await screen.findByRole('heading', { name: '收集结果' })).toBeInTheDocument()
})

it('prevents unloading while the survey draft is dirty', async () => {
  const user = userEvent.setup()
  render(<AdminApp />)
  const title = await screen.findByDisplayValue('DML 使用体验调研')
  await user.type(title, ' 已修改')
  const event = new Event('beforeunload', { cancelable: true })

  window.dispatchEvent(event)

  expect(event.defaultPrevented).toBe(true)
})
