import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  base: './',
  root: resolve('src/renderer'),
  plugins: [react()],
  resolve: {
    alias: {
      '@renderer': resolve('src/renderer/src')
    }
  },
  server: {
    port: 5179,
    strictPort: true,
    host: host || '127.0.0.1',
    hmr: host
      ? {
          protocol: 'ws',
          host,
          port: 5180
        }
      : undefined,
    watch: {
      ignored: ['**/src-tauri/**', '**/dist-tauri/**']
    }
  },
  build: {
    outDir: resolve('dist-tauri'),
    emptyOutDir: true
  }
})
