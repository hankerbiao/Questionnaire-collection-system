import { CalendarX2, ChevronRight, Clock, FileImage, Pencil, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { getMySubmission, getMySubmissions, myAttachmentUrl } from '../../services/userSubmissions'
import type { MySubmissionDetail, MySubmissionRow, SurveySubmission, SubmissionAttachment } from '../../types'

type View = { kind: 'list' } | { kind: 'detail'; id: string }

function AttachmentImage({ detailId, attachments, attachmentId }: { detailId: string; attachments: SubmissionAttachment[]; attachmentId: string }) {
  const match = attachments.find((item) => item.attachmentId === attachmentId)
  if (!match) return <span className="mine-file"><FileImage size={13} />附件已更新，原图不再保留</span>
  if (match.available === false) return <span className="mine-file"><FileImage size={13} />附件已更新，原图不再保留</span>
  return (
    <a className="mine-image" href={myAttachmentUrl(detailId, match.id)} target="_blank" rel="noreferrer">
      <img src={myAttachmentUrl(detailId, match.id)} alt={match.name} />
      <figcaption>{match.name}</figcaption>
    </a>
  )
}

function PayloadSections({ detailId, payload, attachments }: { detailId: string; payload: SurveySubmission; attachments: SubmissionAttachment[] }) {
  return (
    <div className="mine-sections">
      <section><h4>角色与背景</h4><strong>{(payload.profile.roleIds ?? []).join('、') || '未选择'}</strong><p>{payload.profile.roleContext}</p></section>
      <section><h4>重点页面评价</h4>{payload.topPageReviews.map((review) => <article key={review.pageId}><header><strong>{review.pageId}</strong><b>{review.overallScore} 分</b></header><p>优点：{review.strengths}</p><p>槽点：{review.painPoints}</p><pre>{JSON.stringify(review.featureScores, null, 2)}</pre></article>)}</section>
      <section><h4>最高分页复盘</h4><strong>{payload.favoritePageReview.pageId}</strong><p>胜出原因：{payload.favoritePageReview.winningReason}</p><p>仍需改善：{payload.favoritePageReview.improvement}</p></section>
      <section><h4>其余页面评价</h4>{payload.otherPageReviews.map((review) => <article key={review.pageId}><header><strong>{review.pageId}</strong><b>{review.status === 'rated' ? `${review.overallScore} 分` : '未使用 / 不了解'}</b></header>{review.strengths ? <p>优点：{review.strengths}</p> : null}{review.painPoints ? <p>槽点：{review.painPoints}</p> : null}</article>)}</section>
      <section><h4>问题截图说明</h4><p>{payload.issueEvidence.description || '未填写'}</p><div className="mine-images">{payload.issueEvidence.attachments.map((file) => <AttachmentImage key={file.id} detailId={detailId} attachments={attachments} attachmentId={file.id} />)}</div></section>
      <section><h4>遗漏反馈</h4><p>{payload.finalFeedback || '未填写'}</p></section>
    </div>
  )
}

export function MySubmissionsPanel({ onClose, onEdit }: { onClose: () => void; onEdit: (detail: MySubmissionDetail) => void }) {
  const [view, setView] = useState<View>({ kind: 'list' })
  const [rows, setRows] = useState<MySubmissionRow[]>([])
  const [nextCursor, setNextCursor] = useState<string>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<MySubmissionDetail>()
  const [openRevision, setOpenRevision] = useState<number | null>(null)

  const loadList = useCallback(async (append = false, cursor?: string) => {
    setLoading(true)
    setError('')
    try {
      const page = await getMySubmissions(cursor)
      setRows((current) => append ? [...current, ...page.items] : page.items)
      setNextCursor(page.nextCursor)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadList() }, [loadList])

  const openDetail = useCallback(async (id: string) => {
    setLoading(true)
    setError('')
    try {
      const value = await getMySubmission(id)
      setDetail(value)
      setOpenRevision(null)
      setView({ kind: 'detail', id })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="mine-backdrop" onClick={loading ? undefined : onClose}>
      <aside className="mine-panel" onClick={(event) => event.stopPropagation()}>
        <header>
          <div><small>我的提交</small><h2>{view.kind === 'detail' && detail ? detail.submissionId : '填写记录'}</h2></div>
          <button className="icon-control" title="关闭" disabled={loading} onClick={onClose}><X size={18} /></button>
        </header>
        {error ? <div className="admin-error">{error}</div> : null}
        {view.kind === 'list' ? (
          <div className="mine-list">
            {rows.length === 0 && !loading ? <div className="admin-empty">你还没有提交过问卷</div> : null}
            {rows.map((row) => (
              <button key={row.id} type="button" className="mine-row" disabled={loading} onClick={() => void openDetail(row.id)}>
                <div>
                  <strong>{row.submissionId}</strong>
                  <small>{new Date(row.submittedAt).toLocaleString('zh-CN')}{row.updatedAt && row.updatedAt !== row.submittedAt ? ` · 最近修改 ${new Date(row.updatedAt).toLocaleString('zh-CN')}` : ''}</small>
                </div>
                <div className="mine-row-meta">
                  <span><Clock size={13} />第 {row.version} 版</span>
                  {row.revisionCount > 0 ? <span>修改 {row.revisionCount} 次</span> : null}
                  {row.attachmentCount > 0 ? <span>{row.attachmentCount} 张图</span> : null}
                </div>
                <ChevronRight size={16} />
              </button>
            ))}
            {nextCursor ? <button className="admin-button" disabled={loading} onClick={() => void loadList(true, nextCursor)}>加载更多</button> : null}
          </div>
        ) : detail ? (
          <div className="mine-detail">
            <button type="button" className="mine-back" disabled={loading} onClick={() => { setDetail(undefined); setView({ kind: 'list' }) }}>返回列表</button>
            <div className="mine-detail-meta">
              <span>提交时间：{new Date(detail.submittedAt).toLocaleString('zh-CN')}</span>
              <span>当前版本：第 {detail.version} 版</span>
              {detail.revisionCount > 0 ? <span>累计修改 {detail.revisionCount} 次</span> : null}
            </div>
            {detail.surveyClosed ? (
              <div className="mine-closed-tip"><CalendarX2 size={15} />问卷已截止，无法修改本次提交。</div>
            ) : (
              <button type="button" className="admin-primary mine-edit" disabled={loading} onClick={() => onEdit(detail)}><Pencil size={15} />修改本次提交</button>
            )}
            <h3>当前内容</h3>
            <PayloadSections detailId={detail.id} payload={detail.payload} attachments={detail.attachments} />
            {detail.revisions.length > 0 ? (
              <div className="mine-revisions">
                <h3>历史提交内容（{detail.revisions.length} 次）</h3>
                {detail.revisions.slice().reverse().map((revision) => (
                  <div key={revision.index} className="revision-block">
                    <button type="button" className="revision-head" onClick={() => setOpenRevision(openRevision === revision.index ? null : revision.index)}>
                      <span>第 {revision.index} 版</span>
                      <small>{new Date(revision.editedAt).toLocaleString('zh-CN')}</small>
                      <ChevronRight size={15} className={openRevision === revision.index ? 'open' : ''} />
                    </button>
                    {openRevision === revision.index ? <PayloadSections detailId={detail.id} payload={revision.payload} attachments={revision.attachments} /> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </aside>
    </div>
  )
}
