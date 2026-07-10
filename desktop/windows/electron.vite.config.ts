import { resolve } from 'path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        input: {
          index: resolve('src/main/index.ts'),
          // Second entry so vite emits out/main/kgWorker.js alongside index.js.
          // The worker file must be a separate bundle (not inlined) because
          // new Worker(path) needs a real file — it can't load from the main bundle.
          kgWorker: resolve('src/main/ipc/kgWorker.ts')
        }
      }
    }
  },
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
    plugins: [
      react(),
      {
        // onnxruntime-web's wasm binary is self-hosted under public/vad/ (see
        // scripts/copy-vad-assets.mjs) and loaded at runtime via
        // ort.env.wasm.wasmPaths — but vite ALSO emits a 13MB duplicate copy
        // into assets/ (referenced via new URL inside the ort loader, which we
        // never take). Drop the dead-weight asset from the bundle.
        name: 'drop-duplicate-ort-wasm',
        generateBundle(_options, bundle): void {
          for (const key of Object.keys(bundle)) {
            if (/ort-wasm.*\.wasm$/.test(key)) delete bundle[key]
          }
        }
      }
    ]
  }
})
