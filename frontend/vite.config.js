import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const shared = fileURLToPath(new URL('../shared', import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Shared contract fixtures (profile_demo.json) live outside frontend/.
    alias: { '@shared': shared },
  },
  server: {
    fs: { allow: ['.', shared] },
    // Django dev server; the app calls /api/* relative to the page.
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
})
