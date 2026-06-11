import { resolve } from 'path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {},
  preload: {},
  renderer: {
    // Pin the dev server to a fixed port so the renderer's origin
    // (http://localhost:5179) — and therefore its localStorage (onboarding flag,
    // preferences, Firebase session) — stays stable across launches. Without a
    // pinned port, a second worktree holding 5173 pushes this one to 5174, which
    // is a different origin and silently drops all saved state (re-onboarding).
    // strictPort fails fast instead of drifting to a new origin.
    server: {
      port: 5179,
      strictPort: true
    },
    resolve: {
      alias: {
        '@renderer': resolve('src/renderer/src')
      }
    },
    plugins: [react()]
  }
})
