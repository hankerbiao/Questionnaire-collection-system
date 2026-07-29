import { ChevronRight, Download, FileJson, Search, Trash2, UserRound, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { adminApi } from './api'
import type { SubmissionDetail, SubmissionFilterCatalog, SubmissionRow } from './types'

const EMPTY_FILTERS = { keyword: '', username: '', authType: '', role: '', page: '', hasAttachments: '' }

function DetailDrawer({ detail, deleting, deleteError, onClose, onDelete }: { detail: SubmissionDetail; deleting: boolean; deleteError: string; onClose: () => void; onDelete: () => void }) {
  interface DetailPayload {
    profile?: { roleIds?: string[]; roleContext?: string }
    topPageReviews?: Array<{ pageId: string; overallScore: number; strengths: string; painPoints: string; featureScores: Record<string, number> }>
    favoritePageReview?: { pageId: string; winningReason: string; improvement: string }
    otherPageReviews?: Array<{ pageId: string; status: 'rated' | 'unused'; overallScore?: number; strengths: string; painPoints: string }>
    issueEvidence?: { description?: string }
    finalFeedback?: string
  }
  const payload = detail.payload as DetailPayload
  const pageNames = Object.assign({}, ...detail.sections.map((section) => section.pageNames ?? {})) as Record<string, string>
  const topReviews = payload.topPageReviews ?? []
  const otherReviews = payload.otherPageReviews ?? []
  const favoritePageId = payload.favoritePageReview?.pageId ?? ''
  const issueSection = detail.sections.find((section) => section.id === 'issue-evidence')

  return (
    <div className="detail-backdrop" onClick={() => { if (!deleting) onClose() }}>
      <aside className="detail-drawer" onClick={(event) => event.stopPropagation()}>
        <header><div><small>提交详情</small><h2>{detail.submissionId}</h2><p>{new Date(detail.submittedAt).toLocaleString('zh-CN')}</p></div><button className="icon-control" title="关闭" disabled={deleting} onClick={onClose}><X size={18} /></button></header>
        <div className="detail-actions">
          <a className="admin-button" href={adminApi.jsonUrl(detail.id)}><FileJson size={15} />JSON</a>
          <button type="button" className="admin-button danger" disabled={deleting} onClick={onDelete}><Trash2 size={15} />{deleting ? '删除中…' : '删除问卷'}</button>
        </div>
        {deleteError ? <div className="admin-error">{deleteError}</div> : null}
        <div className="detail-sections">
          <section><h3>提交用户</h3>{detail.authType === 'external' ? <><strong>{detail.username}</strong><p>外部用户 ID：{detail.externalUserId}</p></> : <strong>匿名用户</strong>}</section>
          <section><h3>角色与背景</h3><strong>{(payload.profile?.roleIds ?? []).map((id) => detail.roleNames[id] ?? id).join('、')}</strong><p>{payload.profile?.roleContext}</p></section>
          <section><h3>重点页面评价</h3>{topReviews.map((review) => <article key={review.pageId}><header><strong>{pageNames[review.pageId] ?? review.pageId}</strong><b>{review.overallScore} 分</b></header><p>优点：{review.strengths}</p><p>槽点：{review.painPoints}</p><pre>{JSON.stringify(review.featureScores, null, 2)}</pre></article>)}</section>
          <section><h3>最高分页复盘</h3><strong>{pageNames[favoritePageId] ?? favoritePageId}</strong><p>胜出原因：{payload.favoritePageReview?.winningReason}</p><p>仍需改善：{payload.favoritePageReview?.improvement}</p></section>
          <section><h3>其余页面评价</h3>{otherReviews.map((review) => <article key={review.pageId}><header><strong>{pageNames[review.pageId] ?? review.pageId}</strong><b>{review.status === 'rated' ? `${review.overallScore} 分` : '未使用 / 不了解'}</b></header>{review.strengths ? <p>优点：{review.strengths}</p> : null}{review.painPoints ? <p>槽点：{review.painPoints}</p> : null}</article>)}</section>
          <section><h3>问题截图说明</h3><p>{payload.issueEvidence?.description || '未填写'}</p>{issueSection?.attachments?.length ? <div className="detail-images">{issueSection.attachments.map((file) => <figure key={file.id}><a href={adminApi.attachmentUrl(file.id)} target="_blank" rel="noreferrer"><img src={adminApi.attachmentUrl(file.id)} alt={file.name} /></a><figcaption>{file.name}</figcaption></figure>)}</div> : null}</section>
          <section><h3>遗漏反馈</h3><p>{payload.finalFeedback || '未填写'}</p></section>
        </div>
      </aside>
    </div>
  )
}

export function ResultsView() {
  const loadSequence = useRef(0)
  const [stats, setStats] = useState({ total: 0, last7Days: 0, withAttachments: 0 })
  const [catalog, setCatalog] = useState<SubmissionFilterCatalog>()
  const [rows, setRows] = useState<SubmissionRow[]>([])
  const [nextCursor, setNextCursor] = useState<string>()
  const [detail, setDetail] = useState<SubmissionDetail>()
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [error, setError] = useState('')
  const [editingFilters, setEditingFilters] = useState(EMPTY_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS)
  const params = useMemo(() => {
    const result = new URLSearchParams({ limit: '30' })
    Object.entries(appliedFilters).forEach(([key, value]) => value && result.set(key, value))
    return result
  }, [appliedFilters])
  const load = useCallback(async (append = false, cursor?: string) => {
    const sequence = ++loadSequence.current
    setError('')
    try {
      const query = new URLSearchParams(params)
      if (cursor) query.set('cursor', cursor)
      const page = await adminApi.submissions(query)
      if (sequence !== loadSequence.current) return
      setRows((current) => append ? [...current, ...page.items] : page.items)
      setNextCursor(page.nextCursor)
    } catch (reason) {
      if (sequence === loadSequence.current) setError(reason instanceof Error ? reason.message : '加载失败')
    }
  }, [params])

  useEffect(() => {
    Promise.all([adminApi.stats(), adminApi.submissionCatalog()]).then(([nextStats, nextCatalog]) => { setStats(nextStats); setCatalog(nextCatalog) }).catch(() => undefined)
  }, [])
  useEffect(() => { void load() }, [load])

  const deleteSubmission = async () => {
    if (!detail || !window.confirm(`确定删除问卷 ${detail.submissionId} 吗？此操作不可恢复，关联截图也会一并删除。`)) return
    setDeleting(true)
    setDeleteError('')
    setError('')
    try {
      await adminApi.deleteSubmission(detail.id)
      setDetail(undefined)
      const nextStats = await adminApi.stats()
      setStats(nextStats)
      await load()
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : '删除失败')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="admin-view results-view">
      <header className="admin-page-head"><div><h1>收集结果</h1><p>按角色和页面筛选新结构问卷。</p></div><a className="admin-button" href={adminApi.exportUrl(params)}><Download size={16} />导出 CSV</a></header>
      <div className="stat-strip"><div><span>累计提交</span><strong>{stats.total}</strong></div><div><span>最近 7 天</span><strong>{stats.last7Days}</strong></div><div><span>含截图</span><strong>{stats.withAttachments}</strong></div></div>
      <form className="result-filters" onSubmit={(event) => { event.preventDefault(); setAppliedFilters({ ...editingFilters }) }}>
        <label className="admin-search"><Search size={16} /><input placeholder="搜索提交编号、问卷 ID 或用户名" value={editingFilters.keyword} onChange={(event) => setEditingFilters({ ...editingFilters, keyword: event.target.value })} /></label>
        <label className="admin-search"><UserRound size={16} /><input placeholder="精确筛选 username" value={editingFilters.username} onChange={(event) => setEditingFilters({ ...editingFilters, username: event.target.value })} /></label>
        <select aria-label="登录状态筛选" value={editingFilters.authType} onChange={(event) => setEditingFilters({ ...editingFilters, authType: event.target.value })}><option value="">全部用户</option><option value="external">已登录</option><option value="anonymous">匿名</option></select>
        <select aria-label="角色筛选" value={editingFilters.role} onChange={(event) => setEditingFilters({ ...editingFilters, role: event.target.value })}><option value="">全部角色</option>{catalog?.roles.map((role) => <option value={role.id} key={role.id}>{role.label}</option>)}</select>
        <select aria-label="页面筛选" value={editingFilters.page} onChange={(event) => setEditingFilters({ ...editingFilters, page: event.target.value })}><option value="">全部页面</option>{catalog?.pages.map((page) => <option value={page.id} key={page.id}>{page.name}</option>)}</select>
        <select aria-label="附件筛选" value={editingFilters.hasAttachments} onChange={(event) => setEditingFilters({ ...editingFilters, hasAttachments: event.target.value })}><option value="">全部附件状态</option><option value="true">有截图</option><option value="false">无截图</option></select>
        <button className="admin-primary"><Search size={15} />筛选</button>
        <button type="button" className="admin-button" onClick={() => { setEditingFilters(EMPTY_FILTERS); setAppliedFilters(EMPTY_FILTERS) }}><X size={15} />重置</button>
      </form>
      {error ? <div className="admin-error">{error}</div> : null}
      <div className="result-table-wrap"><table className="result-table"><thead><tr><th>提交编号</th><th>用户</th><th>提交时间</th><th>角色</th><th>重点页面</th><th>截图</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id} onClick={() => adminApi.detail(row.id).then((value) => { setDetail(value); setDeleteError('') }).catch((reason) => setError(reason.message))}><td><strong>{row.submissionId}</strong><small>{row.surveyId}</small></td><td>{row.username ?? '匿名'}</td><td>{new Date(row.submittedAt).toLocaleString('zh-CN')}</td><td>{row.roles.map((id) => row.roleNames[id] ?? id).join('、')}</td><td>{row.pages.map((id) => row.pageNames[id] ?? id).join('、')}</td><td>{row.attachmentCount}</td><td><ChevronRight size={16} /></td></tr>)}</tbody></table>{rows.length === 0 ? <div className="admin-empty">暂无符合条件的提交</div> : null}</div>
      <div className="table-footer"><span>已显示 {rows.length} 条</span>{nextCursor ? <button className="admin-button" onClick={() => void load(true, nextCursor)}>加载更多</button> : null}</div>
      {detail ? <DetailDrawer detail={detail} deleting={deleting} deleteError={deleteError} onClose={() => { setDetail(undefined); setDeleteError('') }} onDelete={() => void deleteSubmission()} /> : null}
    </div>
  )
}
