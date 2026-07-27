import { afterEach, describe, expect, it } from 'vitest'
import { createId } from './id'

const originalCrypto = globalThis.crypto

afterEach(() => {
  Object.defineProperty(globalThis, 'crypto', {
    value: originalCrypto,
    configurable: true,
  })
})

describe('createId', () => {
  it('uses the built-in UUID API when available', () => {
    const id = createId('q-', 8)

    expect(id).toMatch(/^q-[0-9a-f]{8}$/)
  })

  it('falls back when randomUUID is unavailable', () => {
    Object.defineProperty(globalThis, 'crypto', {
      value: {
        getRandomValues(bytes: Uint8Array) {
          bytes.fill(0x11)
          return bytes
        },
      },
      configurable: true,
    })

    const id = createId('section-', 8)

    expect(id).toBe('section-11111111')
  })
})
