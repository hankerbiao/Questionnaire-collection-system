import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import App from './App'
import './styles.css'
import './admin/admin.css'

const AdminApp = lazy(() => import('./admin/AdminApp'))
const rootView = window.location.pathname.startsWith('/admin')
  ? <Suspense fallback={<main className="admin-loading">正在加载管理后台…</main>}><AdminApp /></Suspense>
  : <App />

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      {rootView}
    </MotionConfig>
  </StrictMode>,
)
