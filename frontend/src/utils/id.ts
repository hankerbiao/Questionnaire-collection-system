function fallbackUuid() {
  const bytes = new Uint8Array(16)
  const cryptoImpl = globalThis.crypto

  if (cryptoImpl?.getRandomValues) {
    cryptoImpl.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
    return [
      hex.slice(0, 8),
      hex.slice(8, 12),
      hex.slice(12, 16),
      hex.slice(16, 20),
      hex.slice(20),
    ].join('-')
  }

  return `fallback-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export function createId(prefix = '', length?: number) {
  const cryptoImpl = globalThis.crypto
  const uuid = typeof cryptoImpl?.randomUUID === 'function' ? cryptoImpl.randomUUID() : fallbackUuid()
  const value = typeof length === 'number' ? uuid.replace(/-/g, '').slice(0, length) : uuid
  return `${prefix}${value}`
}
