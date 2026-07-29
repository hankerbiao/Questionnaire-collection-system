import { beforeEach, expect, it, vi } from 'vitest'
import { consumeExternalLoginTokenFromUrl, loadUserSession } from './userSession'

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

it('loads an authenticated external user session', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    authenticated: true,
    user: { externalUserId: 'demo-1', username: '张三' },
    ssoEnabled: true,
    loginUrl: null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

  await expect(loadUserSession()).resolves.toEqual({
    authenticated: true,
    user: { externalUserId: 'demo-1', username: '张三' },
    ssoEnabled: true,
    loginUrl: null,
  })
})

it('exchanges an external token and removes it from the browser URL first', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState(null, '', '/?token=signed-token&source=dml')

  await expect(consumeExternalLoginTokenFromUrl()).resolves.toBe(true)

  expect(window.location.pathname + window.location.search).toBe('/?source=dml')
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/external/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: 'signed-token' }),
  })
})

it('does not call the token endpoint without a token parameter', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)

  await expect(consumeExternalLoginTokenFromUrl()).resolves.toBe(false)
  expect(fetchMock).not.toHaveBeenCalled()
})

it('rejects when the session endpoint is unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  await expect(loadUserSession()).rejects.toThrow('无法确认登录状态')
})
