import { ClipboardList, LogOut, Menu, Settings2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { adminApi } from './api'
import { LoginView } from './LoginView'
import { ResultsView } from './ResultsView'
import { SurveyEditor } from './SurveyEditor'
import { type AdminView, useAdminRoute } from './useAdminRoute'

export default function AdminApp() {
  const [username, setUsername] = useState<string>()
  const [checking, setChecking] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const [dirty, setDirty] = useState(false)
  const { view, navigate: navigateView } = useAdminRoute(dirty)

  useEffect(() => {
    adminApi.session()
      .then((value) => setUsername(value.username))
      .catch(() => undefined)
      .finally(() => setChecking(false))
  }, [])

  const navigate = (next: AdminView) => {
    if (navigateView(next)) setMenuOpen(false)
  }

  if (checking) return <main className="admin-loading">正在验证会话…</main>
  if (!username) return <LoginView onLogin={setUsername} />

  return (
    <div className="admin-shell">
      <aside className={menuOpen ? 'admin-sidebar open' : 'admin-sidebar'}>
        <div className="admin-brand"><span>DML</span><strong>问卷管理</strong></div>
        <nav>
          <button className={view === 'results' ? 'active' : ''} onClick={() => navigate('results')}><ClipboardList size={18} />收集结果</button>
          <button className={view === 'survey' ? 'active' : ''} onClick={() => navigate('survey')}><Settings2 size={18} />问卷与目录</button>
        </nav>
        <div className="admin-user"><span><strong>{username}</strong><small>管理员</small></span><button className="icon-control" title="退出" onClick={() => adminApi.logout().finally(() => setUsername(undefined))}><LogOut size={17} /></button></div>
      </aside>
      <div className="admin-content">
        <button className="mobile-menu" onClick={() => setMenuOpen(!menuOpen)}><Menu size={20} /></button>
        {view === 'results' ? <ResultsView /> : <SurveyEditor onDirtyChange={setDirty} />}
      </div>
    </div>
  )
}
