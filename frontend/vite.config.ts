import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBaseUrl = env.VITE_API_BASE_URL?.replace(/\/$/, '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: apiBaseUrl
        ? undefined
        : {
            '/api': env.ROUTEWISE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
          },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test-setup.ts'],
      restoreMocks: true,
    },
  }
})
