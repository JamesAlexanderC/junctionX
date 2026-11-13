import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Django dev server; the chat UI calls /api/* relative to the page.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
