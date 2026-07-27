import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ClipboardCheck,
  LoaderCircle,
  RotateCcw,
} from 'lucide-react'
import { CompletionScreen } from './features/survey/CompletionScreen'
import { createDraft, emptyOtherReview, emptyPageReview, reconcileDraft, selectFavoritePage } from './features/survey/draft'
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
  pruneAttachments,
  putAttachments,
  removeAttachment,
  saveDraft,
  validateAttachmentFiles,
} from './services/storage'
import { buildSubmission, surveyService } from './services/surveyService'
import type {
  AttachmentRecord,
  OtherPageReview,
  PageDefinition,
  PageReview,
  PublishedSurvey,
  SurveyDraft,
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
  const [survey, setSurvey] = useState<PublishedSurvey | null>(null)
  const [draft, setDraft] = useState<SurveyDraft | null>(null)
  const [loadingError, setLoadingError] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submissionId, setSubmissionId] = useState('')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('全部')
  const [previews, setPreviews] = useState<Record<string, string>>({})
  const [attachmentError, setAttachmentError] = useState('')
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    clearLegacyBrowserData()
    Promise.all([loadPublishedSurvey(), getAttachments().catch(() => [])]).then(async ([published, records]) => {
      if (!published) {
        setLoadingError('暂时无法加载问卷，请检查网络后刷新页面。')
        return
      }
      const restored = loadDraft()
      const nextDraft = reconcileDraft(restored ?? createDraft(published.versionId), published)
      const attachmentIds = new Set(nextDraft.attachments.map((attachment) => attachment.id))
      const activeRecords = attachmentRecordsForDraft(records, attachmentIds)
      await pruneAttachments(attachmentIds).catch(() => undefined)
      setSurvey(published)
      setDraft(nextDraft)
      setPreviews(Object.fromEntries(activeRecords.map((record) => [record.id, record.dataUrl])))
    })
  }, [])

  useEffect(() => {
    if (draft) saveDraft(draft)
  }, [draft])

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
  if (!survey || !draft) return <main className="load-state"><LoaderCircle className="spin" size={28} /><p>正在加载问卷…</p></main>

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
      const records = await getAttachments()
      const result = await surveyService.submit(buildSubmission(draft), records)
      setSubmissionId(result.submissionId)
      clearDraft()
      await clearAttachments()
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
      await putAttachments(additions)
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
    await removeAttachment(id).catch(() => undefined)
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
    clearDraft()
    await clearAttachments().catch(() => undefined)
    setPreviews({})
    setDraft(createDraft(survey.versionId))
  }

  if (submissionId) {
    return <CompletionScreen submissionId={submissionId} onRestart={() => { setSubmissionId(''); setDraft(createDraft(survey.versionId)) }} />
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
        <div><span>DML</span><strong>{survey.title}</strong></div>
        <div className="header-progress"><span style={{ width: `${progress}%` }} /></div>
        <button type="button" className="icon-button" title="重新填写" onClick={reset}><RotateCcw size={18} /></button>
      </header>
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
              <button type="button" className="primary-button" disabled={submitting} onClick={goNext}>{submitting ? <><LoaderCircle className="spin" size={17} />正在提交</> : draft.currentStep === 9 ? <>确认提交<Check size={17} /></> : <>下一步<ArrowRight size={17} /></>}</button>
            </footer>
          </article>
        </main>
      </div>
    </div>
  )
}
