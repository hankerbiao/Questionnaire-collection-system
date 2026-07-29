import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App, { CompletionScreen } from './App'
import { selectFavoritePage } from './features/survey/draft'
import { DRAFT_STORAGE_KEY } from './services/storage'
import type { PublishedSurvey, SurveyDraft } from './types'

const survey: PublishedSurvey = {
  versionId: 'version-1', surveyKey: 'dml-v4', version: 1, status: 'published', revision: 1,
  title: 'DML 使用体验调研', description: '',
  roles: [{ id: 'tester', label: '测试人员', description: '执行测试' }],
  pages: ['需求', '用例', '执行', '统计'].map((name, index) => ({
    id: `page-${index}`, name, category: index < 2 ? '需求与用例' : '项目执行', order: index + 1, enabled: true,
    features: [{ id: `feature-${index}`, name: `${name}功能`, description: '', order: 1, enabled: true }],
  })),
}

const storedDraft = (roleContext: string): SurveyDraft => ({
  schemaVersion: 1,
  id: 'stored-draft',
  surveyVersionId: survey.versionId,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  currentStep: 0,
  roleIds: [],
  roleContext,
  topPageIds: [],
  topPageReviews: [],
  favoritePageReview: { pageId: '', winningReason: '', improvement: '' },
  otherPageReviews: [],
  issueDescription: '',
  attachments: [],
  finalFeedback: '',
})

describe('fixed survey flow', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      const body = url.includes('/auth/session')
        ? { authenticated: false, user: null, ssoEnabled: true, loginUrl: null }
        : survey
      return Promise.resolve(new Response(JSON.stringify(body), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }))
    }))
  })

  it('enforces the trimmed 100-character role context boundary', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /测试人员/ }))
    const context = screen.getByPlaceholderText(/至少 100 字/)
    expect((context as HTMLTextAreaElement).value).toContain('1. 我负责哪些项目和团队：')
    expect((context as HTMLTextAreaElement).value).toContain('2. 我通常如何完成任务：')
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('至少需要 100 字')
    await user.clear(context)
    await user.type(context, ` ${'a'.repeat(99)} `)
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('至少需要 100 字')
    await user.clear(context)
    await user.type(context, ` ${'a'.repeat(100)} `)
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    expect(await screen.findByRole('heading', { name: '选择系统内你会用到的页面' })).toBeInTheDocument()
  })

  it.each([
    { saved: '', expected: '1. 我负责哪些项目和团队：' },
    { saved: '这是已经保存的角色与工作背景，不应被预制模板覆盖。', expected: '这是已经保存的角色与工作背景，不应被预制模板覆盖。' },
  ])('reconciles a stored role context without overwriting user content', async ({ saved, expected }) => {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(storedDraft(saved)))

    render(<App />)

    const context = await screen.findByPlaceholderText(/至少 100 字/) as HTMLTextAreaElement
    expect(context.value).toContain(expected)
    if (saved) expect(context.value).toBe(saved)
  })

  it('requires exactly three pages and opens sequential page review', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /测试人员/ }))
    await user.type(screen.getByPlaceholderText(/至少 100 字/), '角色职责和典型工作流程'.repeat(10))
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.click(screen.getByText('需求').closest('button')!)
    await user.click(screen.getByText('用例').closest('button')!)
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('恰好 3 个')
    await user.click(screen.getByText('执行').closest('button')!)
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    expect(await screen.findByRole('heading', { name: '需求' })).toBeInTheDocument()
    expect(screen.getByText('功能点评分')).toBeInTheDocument()
  })

  it('clears favorite review text when the selected page changes', () => {
    const current = { pageId: 'page-0', winningReason: '原来的原因', improvement: '原来的改进' }
    expect(selectFavoritePage(current, 'page-1')).toEqual({
      pageId: 'page-1', winningReason: '', improvement: '',
    })
    expect(selectFavoritePage(current, 'page-0')).toBe(current)
  })

  it('shows the anonymous reward prompt as non-interactive text', async () => {
    render(<App />)
    expect(await screen.findByText('登录填写，有机会获得奖励')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /登录填写，有机会获得奖励/ })).not.toBeInTheDocument()
  })

  it('renders the animated completion state and restarts the survey', async () => {
    const user = userEvent.setup()
    const onRestart = vi.fn()

    render(<CompletionScreen submissionId="DML-TEST-001" onRestart={onRestart} />)

    expect(screen.getByRole('heading', { name: '问卷已提交' })).toHaveFocus()
    expect(screen.getByText('DML-TEST-001')).toBeInTheDocument()
    expect(screen.getAllByTestId('celebration-piece')).toHaveLength(8)
    await user.click(screen.getByRole('button', { name: '填写另一份' }))
    expect(onRestart).toHaveBeenCalledOnce()
  })
})
