import { API_BASE } from '../shared/apiConfig'
import type { UserSession } from '../types'

export async function loadUserSession(): Promise<UserSession> {
  try {
    const response = await fetch(`${API_BASE}/auth/session`)
    if (!response.ok) throw new Error('无法确认登录状态，请刷新页面重试。')
    const body = await response.json() as Partial<UserSession>
    if (typeof body.authenticated !== 'boolean' || typeof body.ssoEnabled !== 'boolean') {
      throw new Error('登录状态响应格式无效。')
    }
    if (body.loginUrl !== null && body.loginUrl !== undefined && typeof body.loginUrl !== 'string') {
      throw new Error('登录入口响应格式无效。')
    }
    const candidate = body.user
    if (body.authenticated && (
      !candidate
      || typeof candidate.externalUserId !== 'string'
      || typeof candidate.username !== 'string'
    )) {
      throw new Error('登录用户响应格式无效。')
    }
    const user = body.authenticated ? candidate! : null
    return {
      authenticated: user !== null,
      user,
      ssoEnabled: body.ssoEnabled,
      loginUrl: typeof body.loginUrl === 'string' ? body.loginUrl : null,
    }
  } catch {
    throw new Error('无法确认登录状态，请检查网络后刷新页面。')
  }
}

export async function consumeExternalLoginTokenFromUrl(): Promise<boolean> {
  const currentUrl = new URL(window.location.href)
  const token = currentUrl.searchParams.get('token')
  if (!token) return false

  currentUrl.searchParams.delete('token')
  window.history.replaceState(
    window.history.state,
    '',
    `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`,
  )

  const response = await fetch(`${API_BASE}/auth/external/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!response.ok) throw new Error('外部系统登录凭证无效或已过期。')
  return true
}

export async function logoutUser(): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  if (!response.ok) throw new Error('退出失败，请稍后重试。')
}
