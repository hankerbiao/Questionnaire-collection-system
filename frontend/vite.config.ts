import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import type { TLSSocket } from 'node:tls'

const apiProxyTarget = process.env.VITE_DEV_API_PROXY || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        xfwd: true,
        configure(proxy) {
          proxy.on('proxyReq', (proxyRequest, request) => {
            const encrypted = (request.socket as TLSSocket).encrypted === true
            const remoteAddress = request.socket.remoteAddress
            const localPort = request.socket.localPort

            // Vite is the forwarding trust boundary; never relay client-supplied values.
            if (request.headers.host) proxyRequest.setHeader('X-Forwarded-Host', request.headers.host)
            else proxyRequest.removeHeader('X-Forwarded-Host')
            proxyRequest.setHeader('X-Forwarded-Proto', encrypted ? 'https' : 'http')
            if (remoteAddress) proxyRequest.setHeader('X-Forwarded-For', remoteAddress)
            else proxyRequest.removeHeader('X-Forwarded-For')
            if (localPort) proxyRequest.setHeader('X-Forwarded-Port', String(localPort))
            else proxyRequest.removeHeader('X-Forwarded-Port')
          })
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
