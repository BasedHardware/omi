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
      // Compile the main-process ENTRY to V8 bytecode in production builds so
      // Electron skips parse/compile of the largest main bundle at boot. This is
      // production-only — electron-vite gates bytecode to `electron-vite build`
      // (NODE_ENV_ELECTRON_VITE==='production'), so `pnpm dev` is untouched — and
      // CJS-only (main output is CJS; if it ever became ESM electron-vite would
      // warn and silently skip). The bytecode is compiled by spawning the
      // installed Electron (ELECTRON_RUN_AS_NODE), so it always matches the
      // shipped V8: an Electron version bump regenerates it on the next build.
      // There is no committed .jsc to go stale.
      //
      // chunkAlias LIMITS compilation to the `index` entry ONLY. It must NOT
      // include:
      //   - `kgWorker` — a SEPARATE entry loaded via `new Worker(kgWorker.js)`
      //     (src/main/ipc/kg.ts). A worker thread has no bytecode loader
      //     registered, so a bytecoded worker entry would fail to load. Keep it
      //     plain JS. (The out/main/chunks/*.mjs ACP/MCP entries are emitted as
      //     ?asset files — type:'asset', not 'chunk' — so bytecode already skips
      //     them; they are spawned as plain-Node children and must stay ESM.)
      //   - the lazy shared chunks (backendTools, mainChatPersonalization) — they
      //     are dynamic imports off the startup path, so bytecoding them yields
      //     ~no boot win and would need extra care that kgWorker never requires a
      //     deleted plaintext chunk.
      bytecode: { chunkAlias: 'index' },
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
  preload: {
    build: {
      // Preload runs with sandbox:false (see the BrowserWindow webPreferences in
      // src/main/index.ts), which bytecode requires — it relies on Node's `vm`
      // module, unavailable in a sandboxed preload. Single CJS entry, no worker,
      // so plain `true` (compile the whole preload) is safe. Production-only, same
      // as main.
      bytecode: true
    }
  },
  renderer: {
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
