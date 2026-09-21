import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 正式接后端时，前端 /api 请求会代理到 FastAPI（127.0.0.1:8000）
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
