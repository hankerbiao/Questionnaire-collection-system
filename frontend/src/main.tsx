import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import App from './App'
import { consumeExternalLoginTokenFromUrl } from './services/userSession'
import './styles.css'
import './admin/admin.css'

const AdminApp = lazy(() => import('./admin/AdminApp'))
const root = createRoot(document.getElementById('root')!)

async function bootstrap() {
  const isAdmin = window.location.pathname.startsWith('/admin')
  if (!isAdmin) await consumeExternalLoginTokenFromUrl()
  const rootView = isAdmin
    ? <Suspense fallback={<main className="admin-loading">正在加载管理后台…</main>}><AdminApp /></Suspense>
    : <App />

  root.render(
    <StrictMode>
      <MotionConfig reducedMotion="user">
        {rootView}
      </MotionConfig>
    </StrictMode>,
  )
}

void bootstrap().catch(() => {
  root.render(
    <main className="load-state">
      <h1>登录失败</h1>
      <p>外部系统登录凭证无效或已过期，请返回原系统重新进入问卷。</p>
    </main>,
  )
})
