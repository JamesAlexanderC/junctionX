import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // recharts is most of the bundle; one ~200 kB gzip chunk is fine here.
    chunkSizeWarningLimit: 800,
  },
  server: {
    // Django dev server; the chat UI calls /api/* relative to the page.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
