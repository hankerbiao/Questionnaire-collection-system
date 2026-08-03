import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ClipboardCheck,
  History,
  LogOut,
  LoaderCircle,
  RotateCcw,
  UserRound,
  X,
} from 'lucide-react'
import { CompletionScreen } from './features/survey/CompletionScreen'
import { ClosedScreen } from './features/survey/ClosedScreen'
import { MySubmissionsPanel } from './features/survey/MySubmissionsPanel'
import { createDraft, draftFromSubmission, emptyOtherReview, emptyPageReview, reconcileDraft, selectFavoritePage } from './features/survey/draft'
import { SurveyStepContent } from './features/survey/SurveyStepContent'
import { validateSurveyStep } from './features/survey/validation'
import { loadPublishedSurvey } from './services/publicSurvey'
import {
  clearAttachments,
  clearDraft,
  clearLegacyBrowserData,
  attachmentRecordsForDraft,
  fileToDataUrl,
  getAttachments,
  loadDraft,
  claimPendingAnonymousDraft,
  ownerKeyForUser,
  pruneAttachments,
  putAttachments,
  removeAttachment,
  saveDraft,
  validateAttachmentFiles,
} from './services/storage'
import { buildSubmission, surveyService } from './services/surveyService'
import { loadUserSession, logoutUser } from './services/userSession'
import type {
  AttachmentRecord,
  MySubmissionDetail,
  OtherPageReview,
  PageDefinition,
  PageReview,
  PublishedSurvey,
  SurveyDraft,
  UserSession,
} from './types'
import { createId } from './utils/id'

export { CompletionScreen } from './features/survey/CompletionScreen'

const STEP_LABELS = [
  '角色与背景',
  '选择常用页面',
  '重点页面 1/3',
  '重点页面 2/3',
  '重点页面 3/3',
  '最高分页复盘',
  '其余页面评价',
  '问题截图说明',
  '遗漏反馈',
  '检查与提交',
]


export default function App() {
  const [userSession, setUserSession] = useState<UserSession | null>(null)
  const [survey, setSurvey] = useState<PublishedSurvey | null>(null)
  const [draft, setDraft] = useState<SurveyDraft | null>(null)
  const [loadingError, setLoadingError] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submissionId, setSubmissionId] = useState('')
  const [mineOpen, setMineOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('全部')
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const [attachmentError, setAttachmentError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [draftNotice, setDraftNotice] = useState('')
  const ownerKey = ownerKeyForUser(userSession?.user?.externalUserId)
  const [editing, setEditing] = useState<{ submissionId: string; version: number } | null>(null)
  const activeOwnerKey = editing ? `${ownerKey}:edit:${editing.submissionId}` : ownerKey

  useEffect(() => {
    clearLegacyBrowserData()
    Promise.all([loadUserSession(), loadPublishedSurvey()]).then(async ([nextSession, published]) => {
      if (!published) throw new Error('暂时无法加载问卷，请检查网络后刷新页面。')
      const nextOwnerKey = ownerKeyForUser(nextSession.user?.externalUserId)
      if (nextSession.user && await claimPendingAnonymousDraft(nextOwnerKey) === 'conflict') {
        setDraftNotice('登录账号已有保存的草稿，当前继续账号草稿；刚才的匿名草稿仍已保留。')
      }
      const records = await getAttachments(nextOwnerKey).catch(() => [])
      const restored = loadDraft(nextOwnerKey)
      const nextDraft = reconcileDraft(restored ?? createDraft(published.versionId), published)
      const attachmentIds = new Set(nextDraft.attachments.map((attachment) => attachment.id))
      const activeRecords = attachmentRecordsForDraft(records, attachmentIds)
      await pruneAttachments(attachmentIds, nextOwnerKey).catch(() => undefined)
      setUserSession(nextSession)
      setSurvey(published)
      setDraft(nextDraft)
      setPreviews(Object.fromEntries(activeRecords.map((record) => [record.id, record.dataUrl])))
    }).catch((reason) => setLoadingError(reason instanceof Error ? reason.message : '问卷加载失败'))
  }, [])

  useEffect(() => {
    if (draft && userSession && !editing) saveDraft(draft, ownerKey)
  }, [draft, ownerKey, userSession, editing])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
    setError('')
    setAttachmentError('')
  }, [draft?.currentStep])

  const enabledPages = useMemo(
    () => survey?.pages.filter((page) => page.enabled).sort((a, b) => a.order - b.order) ?? [],
    [survey],
  )
  const pageById = useMemo(() => new Map(enabledPages.map((page) => [page.id, page])), [enabledPages])
  const topPages = draft?.topPageIds.map((id) => pageById.get(id)).filter((page): page is PageDefinition => Boolean(page)) ?? []
  const highestCandidates = useMemo(() => {
    if (!draft || draft.topPageReviews.some((review) => !review.overallScore)) return []
    const maximum = Math.max(...draft.topPageReviews.map((review) => review.overallScore ?? 0))
    return draft.topPageReviews.filter((review) => review.overallScore === maximum).map((review) => review.pageId)
  }, [draft])

  useEffect(() => {
    if (!draft || highestCandidates.length === 0) return
    const current = draft.favoritePageReview.pageId
    const pageId = highestCandidates.length === 1 ? highestCandidates[0] : highestCandidates.includes(current) ? current : ''
    if (pageId !== current) setDraft({ ...draft, favoritePageReview: selectFavoritePage(draft.favoritePageReview, pageId) })
  }, [draft, highestCandidates])

  if (loadingError) return <main className="load-state"><ClipboardCheck size={32} /><h1>问卷加载失败</h1><p>{loadingError}</p></main>
  if (!survey || !draft || !userSession) return <main className="load-state"><LoaderCircle className="spin" size={28} /><p>正在加载问卷…</p></main>

  if (survey.closedAt && !submissionId) {
    return (
      <ClosedScreen
        title={survey.title}
        closedAt={survey.closedAt}
        canViewMine={Boolean(userSession.user)}
        onViewMine={() => setMineOpen(true)}
      />
    )
  }

  const set = (changes: Partial<SurveyDraft>) => setDraft({ ...draft, ...changes, updatedAt: new Date().toISOString() })
  const updateTopSelection = (pageId: string) => {
    const selected = draft.topPageIds.includes(pageId)
      ? draft.topPageIds.filter((id) => id !== pageId)
      : draft.topPageIds.length < 3 ? [...draft.topPageIds, pageId] : draft.topPageIds
    const previousTop = new Map(draft.topPageReviews.map((review) => [review.pageId, review]))
    const previousOther = new Map(draft.otherPageReviews.map((review) => [review.pageId, review]))
    set({
      topPageIds: selected,
      topPageReviews: selected.map((id) => previousTop.get(id) ?? emptyPageReview(id)),
      otherPageReviews: enabledPages
        .filter((page) => !selected.includes(page.id))
        .map((page) => previousOther.get(page.id) ?? emptyOtherReview(page.id)),
      favoritePageReview: { pageId: '', winningReason: '', improvement: '' },
    })
  }
  const updateTopReview = (index: number, review: PageReview) => {
    const reviews = [...draft.topPageReviews]
    reviews[index] = review
    set({ topPageReviews: reviews })
  }
  const updateOtherReview = (review: OtherPageReview) => set({
    otherPageReviews: draft.otherPageReviews.map((item) => item.pageId === review.pageId ? review : item),
  })

  const validateStep = (step: number): string => {
    return validateSurveyStep(step, draft, enabledPages, topPages)
  }

  const goNext = async () => {
    const stepError = validateStep(draft.currentStep)
    if (stepError) {
      setError(stepError)
      return
    }
    if (draft.currentStep < STEP_LABELS.length - 1) {
      set({ currentStep: draft.currentStep + 1 })
      return
    }
    for (let step = 0; step < STEP_LABELS.length - 1; step += 1) {
      const invalid = validateStep(step)
      if (invalid) {
        set({ currentStep: step })
        setError(invalid)
        return
      }
    }
    setSubmitting(true)
    try {
      const records = await getAttachments(activeOwnerKey)
      if (editing) {
        await surveyService.edit(editing.submissionId, buildSubmission(draft), records, editing.version)
        await clearAttachments(activeOwnerKey).catch(() => undefined)
        setEditing(null)
        setMineOpen(true)
      } else {
        const result = await surveyService.submit(buildSubmission(draft), records)
        setSubmissionId(result.submissionId)
        clearDraft(ownerKey)
        await clearAttachments(ownerKey)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '提交失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  const upload = async (files: FileList) => {
    const incoming = Array.from(files)
    const invalid = validateAttachmentFiles(incoming, draft.attachments.length)
    if (invalid) return setAttachmentError(invalid)
    setUploading(true)
    try {
      const additions: AttachmentRecord[] = []
      for (const file of incoming) {
        const record: AttachmentRecord = {
          id: createId(),
          questionId: 'issue-evidence',
          name: file.name,
          type: file.type,
          size: file.size,
          dataUrl: await fileToDataUrl(file),
        }
        additions.push(record)
      }
      await putAttachments(additions, activeOwnerKey)
      const attachmentMetas = additions.map((item) => ({
          id: item.id,
          questionId: item.questionId,
          name: item.name,
          type: item.type,
          size: item.size,
      }))
      setDraft((current) => current ? {
        ...current,
        attachments: [...current.attachments, ...attachmentMetas],
        updatedAt: new Date().toISOString(),
      } : current)
      setPreviews((current) => ({ ...current, ...Object.fromEntries(additions.map((item) => [item.id, item.dataUrl])) }))
    } catch {
      setAttachmentError('截图无法保存到浏览器，请检查本地存储权限。')
    } finally {
      setUploading(false)
    }
  }

  const remove = async (id: string) => {
    await removeAttachment(id, activeOwnerKey).catch(() => undefined)
    setPreviews((current) => {
      const next = { ...current }
      delete next[id]
      return next
    })
    setDraft((current) => current ? {
      ...current,
      attachments: current.attachments.filter((item) => item.id !== id),
      updatedAt: new Date().toISOString(),
    } : current)
  }

  const reset = async () => {
    if (!window.confirm('确定清除当前答案和截图并重新开始吗？')) return
    clearDraft(ownerKey)
    await clearAttachments(ownerKey).catch(() => undefined)
    setPreviews({})
    setDraft(createDraft(survey.versionId))
  }

  const startEdit = (detail: MySubmissionDetail) => {
    setEditing({ submissionId: detail.id, version: detail.version })
    setDraft(draftFromSubmission(detail.payload))
    setMineOpen(false)
  }

  const cancelEdit = () => {
    void clearAttachments(activeOwnerKey).catch(() => undefined)
    setEditing(null)
    setDraft(reconcileDraft(loadDraft(ownerKey) ?? createDraft(survey.versionId), survey))
  }

  if (submissionId) {
    return <CompletionScreen submissionId={submissionId} onRestart={() => { setSubmissionId(''); setDraft(createDraft(survey.versionId)) }} onViewMine={userSession.user ? () => setMineOpen(true) : undefined} />
  }

  const progress = ((draft.currentStep + 1) / STEP_LABELS.length) * 100
  const currentTopPage = draft.currentStep >= 2 && draft.currentStep <= 4 ? topPages[draft.currentStep - 2] : undefined
  const currentTopReview = draft.currentStep >= 2 && draft.currentStep <= 4 ? draft.topPageReviews[draft.currentStep - 2] : undefined
  const categories = ['全部', ...new Set(enabledPages.map((page) => page.category))]
  const filteredPages = enabledPages.filter((page) =>
    (category === '全部' || page.category === category)
    && page.name.toLowerCase().includes(search.trim().toLowerCase()),
  )
  return (
    <div className="survey-app">
      <header className="app-header">
        <div><span>DML</span><strong>{survey.title}</strong>{editing ? <span className="edit-badge">修改中（第 {editing.version} 版）</span> : null}</div>
        <div className="header-progress"><span style={{ width: `${progress}%` }} /></div>
        <div className="header-actions">
          {userSession.user ? (
            <div className="signed-user"><UserRound size={17} /><strong>{userSession.user.username}</strong></div>
          ) : userSession.ssoEnabled ? (
            <span className="login-message">登录填写，有机会获得奖励</span>
          ) : <span className="anonymous-user">匿名填写</span>}
          {userSession.user ? <button type="button" className="icon-button" title="我的提交" onClick={() => setMineOpen(true)}><History size={18} /></button> : null}
          {editing ? <button type="button" className="icon-button" title="取消修改" onClick={cancelEdit}><X size={18} /></button> : null}
          {userSession.user ? <button type="button" className="icon-button" title="退出登录" onClick={() => logoutUser().then(() => window.location.reload()).catch((reason) => setError(reason.message))}><LogOut size={18} /></button> : null}
          <button type="button" className="icon-button" title="重新填写" onClick={reset}><RotateCcw size={18} /></button>
        </div>
      </header>
      {draftNotice ? <div className="draft-notice" role="status">{draftNotice}</div> : null}
      <div className="survey-layout">
        <aside className="step-rail" aria-label="问卷进度">
          {STEP_LABELS.map((label, index) => (
            <button type="button" key={label} className={`${index === draft.currentStep ? 'active' : ''} ${index < draft.currentStep ? 'done' : ''}`} onClick={() => index <= draft.currentStep && set({ currentStep: index })}>
              <span>{index < draft.currentStep ? <Check size={14} /> : index + 1}</span>{label}
            </button>
          ))}
        </aside>
        <main className="survey-main">
          <div className="mobile-step">{STEP_LABELS[draft.currentStep]}<span>{draft.currentStep + 1} / {STEP_LABELS.length}</span></div>
          <article className="question-stage">
            <SurveyStepContent
              survey={survey}
              draft={draft}
              pageById={pageById}
              currentTopPage={currentTopPage}
              currentTopReview={currentTopReview}
              highestCandidates={highestCandidates}
              categories={categories}
              filteredPages={filteredPages}
              search={search}
              category={category}
              previews={previews}
              attachmentError={attachmentError}
              uploading={uploading}
              updateDraft={set}
              setSearch={setSearch}
              setCategory={setCategory}
              updateTopSelection={updateTopSelection}
              updateTopReview={updateTopReview}
              updateOtherReview={updateOtherReview}
              upload={upload}
              remove={remove}
            />

            {error ? <p className="validation-message" role="alert">{error}</p> : null}
            <footer className="question-footer">
              <button type="button" className="secondary-button" disabled={draft.currentStep === 0 || submitting} onClick={() => set({ currentStep: draft.currentStep - 1 })}><ArrowLeft size={17} />返回</button>
              <button type="button" className="primary-button" disabled={submitting} onClick={goNext}>{submitting ? <><LoaderCircle className="spin" size={17} />{editing ? '正在保存' : '正在提交'}</> : draft.currentStep === 9 ? (editing ? <>保存修改<Check size={17} /></> : <>确认提交<Check size={17} /></>) : <>下一步<ArrowRight size={17} /></>}</button>
            </footer>
          </article>
        </main>
      </div>
      {mineOpen ? <MySubmissionsPanel onClose={() => setMineOpen(false)} onEdit={startEdit} /> : null}
    </div>
  )
}
