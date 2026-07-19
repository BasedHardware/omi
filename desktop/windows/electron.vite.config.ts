import { resolve } from 'path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'
import { resolveDevInstance } from './src/main/devInstance'

// Resolve THIS checkout's dev instance from the worktree it lives in. The primary
// checkout stays on 5179 with the default profile (zero change). A linked worktree
// derives its own renderer port so several `pnpm dev` sessions coexist. We also
// stamp the instance into the env so the spawned Electron main process applies the
// matching CDP port + window-title suffix + userData profile; the main process
// re-derives from its own cwd as a fallback, so correctness never depends on this.
const devInstance = resolveDevInstance()
process.env.OMI_INSTANCE = devInstance.name
process.env.OMI_DEV_CDP_PORT = String(devInstance.cdpPort)
if (!devInstance.isPrimary && !process.env.OMI_SANDBOX) {
  // Auto-isolate the linked worktree's userData (dev/bench.ts reads OMI_SANDBOX).
  process.env.OMI_SANDBOX = devInstance.name
}

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
    build: {
      // Multi-page renderer: the main window loads index.html (the full SPA), while
      // each auxiliary window loads its own slim HTML entry that imports ONLY the
      // component tree it renders — not the whole app graph (three.js orb,
      // onnxruntime, every page). Each aux window used to load index.html and pay a
      // full ~200 MB SPA renderer; per-entry inputs let rollup tree-shake each
      // window down to what it uses. The main-process window loaders point at these
      // htmls (glow/glowWindow.ts, insight/toastWindow.ts, captureWindow.ts),
      // keeping the same `#/<route>` hash so window-role + IPC sender detection are
      // unchanged. See perf/win-slim-aux-windows.
      rollupOptions: {
        input: {
          index: resolve('src/renderer/index.html'),
          glow: resolve('src/renderer/glow.html'),
          'insight-toast': resolve('src/renderer/insight-toast.html'),
          capture: resolve('src/renderer/capture.html')
        }
      }
    },
    // Pin the dev server to this instance's port so the renderer's origin — and
    // therefore its localStorage (onboarding flag, preferences, Firebase session)
    // — stays stable across launches. The PRIMARY checkout keeps 5179; a linked
    // worktree derives its own port (5180–5279) from its folder name so parallel
    // `pnpm dev` sessions never share an origin (which would silently drop saved
    // state) or fight over one port. strictPort fails LOUD on a collision instead
    // of drifting to a new origin. Override with OMI_DEV_PORT / OMI_INSTANCE.
    // See src/main/devInstance.ts + docs/multi-worktree-dev.md.
    server: {
      port: devInstance.rendererPort,
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
