import { CalendarX2, Check, GripVertical, Plus, Save, Trash2, Unlock, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { PageDefinition, PageFeatureDefinition, RoleDefinition } from '../types'
import { createId } from '../utils/id'
import { adminApi } from './api'
import type { SurveyVersionConfig } from './types'

const newPage = (order: number): PageDefinition => ({ id: createId('page-', 8), name: '新页面', category: '未分类', order, enabled: true, features: [] })
const newFeature = (order: number): PageFeatureDefinition => ({ id: createId('feature-', 8), name: '新功能点', description: '', order, enabled: true })
const newRole = (): RoleDefinition => ({ id: createId('role-', 8), label: '新角色', description: '' })

export function SurveyEditor({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const [draft, setDraft] = useState<SurveyVersionConfig>()
  const [baseline, setBaseline] = useState('')
  const [published, setPublished] = useState<{ version: number; closedAt?: string | null }>()
  const [selectedPage, setSelectedPage] = useState(0)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const dirty = Boolean(draft && JSON.stringify(draft) !== baseline)
  useEffect(() => { onDirtyChange(dirty) }, [dirty, onDirtyChange])
  useEffect(() => {
    adminApi.draft()
      .then((value) => { setDraft(value); setBaseline(JSON.stringify(value)) })
      .catch((reason) => setMessage(reason.message))
    adminApi.versions()
      .then((items) => { const current = items.find((item) => item.status === 'published'); if (current) setPublished({ version: current.version, closedAt: current.closedAt }) })
      .catch(() => undefined)
  }, [])
  const refreshPublished = useCallback(async () => {
    const items = await adminApi.versions()
    const current = items.find((item) => item.status === 'published')
    if (current) setPublished({ version: current.version, closedAt: current.closedAt })
  }, [])
  if (!draft) return <div className="admin-loading">{message || '正在加载问卷草稿…'}</div>
  const page = draft.pages[selectedPage]
  const updatePage = (next: PageDefinition) => setDraft({ ...draft, pages: draft.pages.map((item, index) => index === selectedPage ? next : item) })
  const save = async () => {
    if (busy) return
    setBusy(true)
    try { const next = await adminApi.saveDraft(draft); setDraft(next); setBaseline(JSON.stringify(next)); setMessage('草稿已保存') }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : '保存失败') }
    finally { setBusy(false) }
  }
  const publish = async () => {
    if (busy || !confirm('发布后会生成新版本并立即用于新问卷，确认继续？')) return
    setBusy(true)
    try {
      const current = dirty ? await adminApi.saveDraft(draft) : draft
      const publishedVersion = await adminApi.publish(current.revision)
      const next = await adminApi.draft()
      setDraft(next); setBaseline(JSON.stringify(next)); setMessage(`版本 ${publishedVersion.version} 已发布`)
      await refreshPublished()
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : '发布失败') }
    finally { setBusy(false) }
  }
  const toggleClosed = async () => {
    const closing = !published?.closedAt
    if (busy || !confirm(closing
      ? '截止后用户将无法提交新问卷（已提交记录不受影响），确认继续？'
      : '重新开启后用户可以继续提交，确认继续？')) return
    setBusy(true)
    try {
      const next = closing ? await adminApi.closeCollection() : await adminApi.reopenCollection()
      setPublished({ version: next.version, closedAt: next.closedAt })
      setMessage(closing ? '问卷收集已截止' : '问卷收集已重新开启')
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : '操作失败') }
    finally { setBusy(false) }
  }
  const movePage = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= draft.pages.length) return
    const pages = [...draft.pages]
    ;[pages[index], pages[target]] = [pages[target], pages[index]]
    pages.forEach((item, position) => { item.order = position + 1 })
    setDraft({ ...draft, pages }); setSelectedPage(target)
  }

  return (
    <div className="admin-view catalog-editor">
      <header className="admin-page-head"><div><h1>问卷与页面目录</h1><p>固定问卷流程 · 草稿修订 {draft.revision} · {busy ? '正在处理' : dirty ? '有未保存修改' : '已保存'} · {published?.closedAt ? `已截止（${new Date(published.closedAt).toLocaleString('zh-CN')}）` : '收集中'}</p></div><div><button className="admin-button" disabled={!dirty || busy} onClick={save}><Save size={16} />保存草稿</button><button className={published?.closedAt ? 'admin-button' : 'admin-button danger'} disabled={busy || !published} onClick={toggleClosed}>{published?.closedAt ? <><Unlock size={16} />重新开启</> : <><CalendarX2 size={16} />截止收集</>}</button><button className="admin-primary" disabled={busy} onClick={publish}><Check size={16} />发布版本</button></div></header>
      {message ? <div className="admin-message">{message}<button onClick={() => setMessage('')}><X size={14} /></button></div> : null}
      <fieldset className="editor-body" disabled={busy}>
        <section className="survey-basics"><label><span>问卷标题</span><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label><span>问卷说明</span><textarea rows={3} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label></section>
        <section className="role-editor"><header><div><h2>角色</h2><p>角色将用于第一题多选和后台筛选。</p></div><button className="admin-button" onClick={() => setDraft({ ...draft, roles: [...draft.roles, newRole()] })}><Plus size={15} />添加角色</button></header>{draft.roles.map((role, index) => <div key={role.id}><code>{role.id}</code><input aria-label="角色名称" value={role.label} onChange={(event) => setDraft({ ...draft, roles: draft.roles.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item) })} /><input aria-label="角色说明" value={role.description} onChange={(event) => setDraft({ ...draft, roles: draft.roles.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item) })} /><button className="icon-control danger" title="删除角色" onClick={() => setDraft({ ...draft, roles: draft.roles.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 size={15} /></button></div>)}</section>
        <div className="catalog-grid">
          <aside className="page-tree"><header><div><strong>页面目录</strong><small>{draft.pages.filter((item) => item.enabled).length} 个启用页面</small></div><button className="icon-control" title="添加页面" onClick={() => { setDraft({ ...draft, pages: [...draft.pages, newPage(draft.pages.length + 1)] }); setSelectedPage(draft.pages.length) }}><Plus size={16} /></button></header>{draft.pages.map((item, index) => <button key={item.id} className={index === selectedPage ? 'active' : ''} onClick={() => setSelectedPage(index)}><GripVertical size={14} /><span><strong>{item.name}</strong><small>{item.category} · {item.features.filter((feature) => feature.enabled).length} 个功能点{item.enabled ? '' : ' · 已停用'}</small></span></button>)}</aside>
          {page ? <main className="page-properties">
            <header><div><h2>{page.name}</h2><code>{page.id}</code></div><div><button className="admin-button" onClick={() => movePage(selectedPage, -1)}>上移</button><button className="admin-button" onClick={() => movePage(selectedPage, 1)}>下移</button><button className="admin-button danger" onClick={() => { if (confirm('删除这个页面及全部功能点？')) { setDraft({ ...draft, pages: draft.pages.filter((_, index) => index !== selectedPage) }); setSelectedPage(Math.max(0, selectedPage - 1)) } }}><Trash2 size={15} />删除</button></div></header>
            <div className="page-fields"><label><span>页面名称</span><input value={page.name} onChange={(event) => updatePage({ ...page, name: event.target.value })} /></label><label><span>分类</span><input value={page.category} onChange={(event) => updatePage({ ...page, category: event.target.value })} /></label><label className="toggle"><input type="checkbox" checked={page.enabled} onChange={(event) => updatePage({ ...page, enabled: event.target.checked })} />启用页面</label></div>
            <section className="feature-editor"><header><div><h3>功能点</h3><p>重点页面评价会要求用户为每个启用功能点评分。</p></div><button className="admin-button" onClick={() => updatePage({ ...page, features: [...page.features, newFeature(page.features.length + 1)] })}><Plus size={15} />添加功能点</button></header>{page.features.map((feature, index) => <div className="feature-item" key={feature.id}><code>{feature.id}</code><input aria-label="功能点名称" value={feature.name} onChange={(event) => updatePage({ ...page, features: page.features.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} /><textarea aria-label="功能点说明" rows={2} value={feature.description} onChange={(event) => updatePage({ ...page, features: page.features.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item) })} /><label><input type="checkbox" checked={feature.enabled} onChange={(event) => updatePage({ ...page, features: page.features.map((item, itemIndex) => itemIndex === index ? { ...item, enabled: event.target.checked } : item) })} />启用</label><button className="icon-control danger" title="删除功能点" onClick={() => updatePage({ ...page, features: page.features.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 size={15} /></button></div>)}</section>
          </main> : null}
        </div>
      </fieldset>
    </div>
  )
}
