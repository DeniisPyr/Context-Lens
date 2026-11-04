import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'API_')

  return {
    plugins: [react()],
    server: {
      // Forward API calls to the FastAPI dev server so the browser sees one origin (no CORS in dev).
      proxy: {
        '/api': env.API_PROXY_TARGET || 'http://localhost:8000',
      },
    },
    test: {
      environment: 'jsdom',
      // Keep the CSS in tests, so src/test/setup.ts can apply it to the page.
      css: true,
      setupFiles: './src/test/setup.ts',
    },
  }
})
