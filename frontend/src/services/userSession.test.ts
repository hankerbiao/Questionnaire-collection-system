import { expect, it, vi } from 'vitest'
import { loadUserSession } from './userSession'

it('loads an authenticated external user session', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    authenticated: true,
    user: { externalUserId: 'demo-1', username: '张三' },
    ssoEnabled: true,
    loginUrl: 'http://external.test',
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

  await expect(loadUserSession()).resolves.toEqual({
    authenticated: true,
    user: { externalUserId: 'demo-1', username: '张三' },
    ssoEnabled: true,
    loginUrl: 'http://external.test',
  })
})

it('rejects when the session endpoint is unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  await expect(loadUserSession()).rejects.toThrow('无法确认登录状态')
})
