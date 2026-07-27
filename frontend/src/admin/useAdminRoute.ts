import { useCallback, useEffect, useState } from 'react'

export type AdminView = 'results' | 'survey'

const viewFromPath = (): AdminView => location.pathname.includes('/surveys') ? 'survey' : 'results'
const pathForView = (view: AdminView) => view === 'results' ? '/admin/results' : '/admin/surveys'

export function useAdminRoute(dirty: boolean) {
  const [view, setView] = useState<AdminView>(viewFromPath)

  const confirmLeave = useCallback(() => (
    !dirty || confirm('问卷草稿有未保存修改，确定离开？')
  ), [dirty])

  const navigate = useCallback((next: AdminView) => {
    if (next === view || !confirmLeave()) return false
    history.pushState({}, '', pathForView(next))
    setView(next)
    return true
  }, [confirmLeave, view])

  useEffect(() => {
    const onPopState = () => {
      const next = viewFromPath()
      if (next === view) return
      if (!confirmLeave()) {
        history.replaceState({}, '', pathForView(view))
        return
      }
      setView(next)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [confirmLeave, view])

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  return { view, navigate }
}
