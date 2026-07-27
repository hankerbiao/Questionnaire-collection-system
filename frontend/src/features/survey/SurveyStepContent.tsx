import { Search } from 'lucide-react'
import { AttachmentUpload } from '../../components/AttachmentUpload'
import type { OtherPageReview, PageDefinition, PageReview, PublishedSurvey, SurveyDraft } from '../../types'
import { selectFavoritePage } from './draft'
import { ReviewEditor, ScorePicker, TextArea } from './SurveyFields'

interface SurveyStepContentProps {
  survey: PublishedSurvey
  draft: SurveyDraft
  pageById: Map<string, PageDefinition>
  currentTopPage?: PageDefinition
  currentTopReview?: PageReview
  highestCandidates: string[]
  categories: string[]
  filteredPages: PageDefinition[]
  search: string
  category: string
  previews: Record<string, string>
  attachmentError: string
  uploading: boolean
  updateDraft: (changes: Partial<SurveyDraft>) => void
  setSearch: (value: string) => void
  setCategory: (value: string) => void
  updateTopSelection: (pageId: string) => void
  updateTopReview: (index: number, review: PageReview) => void
  updateOtherReview: (review: OtherPageReview) => void
  upload: (files: FileList) => Promise<void>
  remove: (id: string) => Promise<void>
}

export function SurveyStepContent({
  survey, draft, pageById, currentTopPage, currentTopReview, highestCandidates,
  categories, filteredPages, search, category, previews, attachmentError, uploading,
  updateDraft, setSearch, setCategory, updateTopSelection, updateTopReview,
  updateOtherReview, upload, remove,
}: SurveyStepContentProps) {
  const favorite = draft.favoritePageReview

  return (
    <>
      {draft.currentStep === 0 ? (
        <>
          <header className="question-heading"><small>角色与使用背景</small><h1>你主要以什么角色使用 DML？</h1><p>可多选。补充说明请描述你的职责、典型工作流程，以及使用 DML 的目的。</p></header>
          <div className="option-grid">
            {survey.roles.map((role) => <button type="button" key={role.id} className={draft.roleIds.includes(role.id) ? 'selected' : ''} onClick={() => updateDraft({ roleIds: draft.roleIds.includes(role.id) ? draft.roleIds.filter((id) => id !== role.id) : [...draft.roleIds, role.id] })}><strong>{role.label}</strong><small>{role.description}</small></button>)}
          </div>
          <TextArea label="其他 / 补充说明" required maxLength={1000} rows={10} value={draft.roleContext} onChange={(roleContext) => updateDraft({ roleContext })} placeholder="请根据模板填写，去除首尾空白后至少 100 字。" />
        </>
      ) : null}

      {draft.currentStep === 1 ? (
        <>
          <header className="question-heading"><small>使用范围</small><h1>选择系统内你会用到的页面</h1><p>请选择恰好 3 个最常用的页面。选择顺序仅决定后续展示顺序，不代表排名。</p></header>
          <div className="catalog-toolbar">
            <label><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索页面" /></label>
            <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="页面分类">{categories.map((item) => <option key={item}>{item}</option>)}</select>
            <strong>已选 {draft.topPageIds.length} / 3</strong>
          </div>
          <div className="page-catalog">
            {filteredPages.map((page) => {
              const selectedIndex = draft.topPageIds.indexOf(page.id)
              return <button type="button" key={page.id} className={selectedIndex >= 0 ? 'selected' : ''} disabled={selectedIndex < 0 && draft.topPageIds.length === 3} onClick={() => updateTopSelection(page.id)}><span>{selectedIndex >= 0 ? selectedIndex + 1 : null}</span><strong>{page.name}</strong><small>{page.category} · {page.features.filter((feature) => feature.enabled).length} 个功能点</small></button>
            })}
          </div>
        </>
      ) : null}

      {currentTopPage && currentTopReview ? (
        <>
          <header className="question-heading"><small>重点页面 {draft.currentStep - 1}/3</small><h1>{currentTopPage.name}</h1><p>请评价整体体验和每个功能点，再留下具体的优点与槽点。</p></header>
          <ReviewEditor page={currentTopPage} review={currentTopReview} onChange={(review) => updateTopReview(draft.currentStep - 2, review)} />
        </>
      ) : null}

      {draft.currentStep === 5 ? (
        <>
          <header className="question-heading"><small>最高分页复盘</small><h1>为什么这个页面得分最高？</h1><p>最高综合分已由系统计算。并列时，请从并列页面中选择一个进行复盘。</p></header>
          <div className="favorite-summary">
            {highestCandidates.map((pageId) => <button type="button" key={pageId} className={favorite.pageId === pageId ? 'selected' : ''} onClick={() => updateDraft({ favoritePageReview: selectFavoritePage(favorite, pageId) })}><strong>{pageById.get(pageId)?.name}</strong><span>{draft.topPageReviews.find((review) => review.pageId === pageId)?.overallScore} 分</span></button>)}
          </div>
          <div className="two-column-fields">
            <TextArea label="它胜出的原因" required value={favorite.winningReason} onChange={(winningReason) => updateDraft({ favoritePageReview: { ...favorite, winningReason } })} placeholder="哪些功能、流程或信息呈现让它明显更好？" />
            <TextArea label="仍需改善之处" required value={favorite.improvement} onChange={(improvement) => updateDraft({ favoritePageReview: { ...favorite, improvement } })} placeholder="即便是最高分页面，最值得优先修正的是什么？" />
          </div>
        </>
      ) : null}

      {draft.currentStep === 6 ? (
        <>
          <header className="question-heading"><small>其余页面评价</small><h1>其他页面的整体体验</h1><p>默认是“未使用 / 不了解”。使用过的页面请选择 1–10 分，优点和槽点可选。</p></header>
          <div className="other-pages">
            {draft.otherPageReviews.map((review) => {
              const page = pageById.get(review.pageId)
              if (!page) return null
              return <section key={page.id} className={review.status === 'rated' ? 'rated' : ''}><header><div><strong>{page.name}</strong><small>{page.category}</small></div><label><input type="checkbox" checked={review.status === 'rated'} onChange={(event) => updateOtherReview({ ...review, status: event.target.checked ? 'rated' : 'unused', overallScore: event.target.checked ? review.overallScore : undefined })} />使用过</label></header>{review.status === 'rated' ? <><ScorePicker label={`${page.name}综合分`} value={review.overallScore} onChange={(overallScore) => updateOtherReview({ ...review, overallScore })} /><div className="two-column-fields compact"><TextArea rows={3} label="优点" value={review.strengths} onChange={(strengths) => updateOtherReview({ ...review, strengths })} /><TextArea rows={3} label="槽点" value={review.painPoints} onChange={(painPoints) => updateOtherReview({ ...review, painPoints })} /></div></> : <p>未使用 / 不了解</p>}</section>
            })}
          </div>
        </>
      ) : null}

      {draft.currentStep === 7 ? (
        <>
          <header className="question-heading"><small>问题证据</small><h1>问题截图说明</h1><p>截图可选，最多 3 张。上传截图后必须填写问题说明。</p></header>
          <AttachmentUpload attachments={draft.attachments} previews={previews} error={attachmentError} disabled={uploading} onUpload={upload} onRemove={remove} />
          <TextArea label="问题说明" required={draft.attachments.length > 0} value={draft.issueDescription} onChange={(issueDescription) => updateDraft({ issueDescription })} placeholder="请说明截图中的页面、操作步骤、实际结果和期望结果。" />
        </>
      ) : null}

      {draft.currentStep === 8 ? (
        <><header className="question-heading"><small>开放反馈</small><h1>关于 DML，还有哪些我们没有问到？</h1><p>可以补充未覆盖的需求、协作问题或你对新版本的期待。</p></header><TextArea label="补充反馈" maxLength={2000} rows={10} value={draft.finalFeedback} onChange={(finalFeedback) => updateDraft({ finalFeedback })} /></>
      ) : null}

      {draft.currentStep === 9 ? (
        <>
          <header className="question-heading"><small>检查与提交</small><h1>确认你的反馈</h1><p>提交前请快速检查重点页面和截图说明。</p></header>
          <div className="review-summary">
            <section><h2>角色</h2><p>{draft.roleIds.map((id) => survey.roles.find((role) => role.id === id)?.label).join('、')}</p><blockquote>{draft.roleContext}</blockquote></section>
            <section><h2>重点页面</h2>{draft.topPageReviews.map((review) => <div key={review.pageId}><strong>{pageById.get(review.pageId)?.name}</strong><span>{review.overallScore} 分</span><p>优点：{review.strengths}</p><p>槽点：{review.painPoints}</p></div>)}</section>
            <section><h2>最高分页</h2><p>{pageById.get(favorite.pageId)?.name}：{favorite.winningReason}</p></section>
            <section><h2>其余页面</h2><p>已评价 {draft.otherPageReviews.filter((review) => review.status === 'rated').length} 个，未使用 / 不了解 {draft.otherPageReviews.filter((review) => review.status === 'unused').length} 个</p></section>
            <section><h2>问题证据</h2><p>{draft.attachments.length} 张截图{draft.issueDescription ? `：${draft.issueDescription}` : ''}</p></section>
          </div>
        </>
      ) : null}
    </>
  )
}
