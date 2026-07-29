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
    if (body.ssoEnabled && typeof body.loginUrl !== 'string') {
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

export async function logoutUser(): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  if (!response.ok) throw new Error('退出失败，请稍后重试。')
}
