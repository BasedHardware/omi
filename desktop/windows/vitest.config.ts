import { defineConfig, type Plugin } from 'vitest/config'
import { loadEnv } from 'vite'
import { dirname, resolve } from 'path'

// Real values when the developer has a .env; empty strings in CI, which has none.
const localEnv = loadEnv('test', __dirname, 'VITE_')

// electron-vite's `?asset` imports (a file path resolved at build time) don't
// exist in plain vitest. Resolve them to the real on-disk source path so
// main-process modules that import bundled assets (e.g. the coding-agent ACP
// entry script) stay testable — tests can even spawn the resolved file.
const assetSuffixPlugin: Plugin = {
  name: 'electron-vite-asset-stub',
  enforce: 'pre',
  resolveId(source, importer) {
    if (!source.endsWith('?asset')) return null
    const clean = source.slice(0, -'?asset'.length)
    const resolved = importer ? resolve(dirname(importer), clean) : resolve(clean)
    return `\0asset:${resolved}`
  },
  load(id) {
    if (!id.startsWith('\0asset:')) return null
    return `export default ${JSON.stringify(id.slice('\0asset:'.length))}`
  }
}

export default defineConfig({
  plugins: [assetSuffixPlugin],
  resolve: {
    alias: {
      // Node-side suites import main-process modules whose graph pulls in
      // `electron`, whose real entry needs the native binary. Alias to a stub.
      electron: resolve(__dirname, 'test/electronStub.ts')
    }
  },
  test: {
    // Firebase config for tests. `lib/firebase.ts` builds `auth` AT MODULE IMPORT
    // (deliberately — persistence must be set synchronously so a reloaded window
    // rehydrates its session deterministically), and the Firebase SDK validates
    // the API key right there. So ANY suite that transitively imports that module
    // needs a key to merely be importable, even though no test ever talks to
    // Firebase.
    //
    // Developers have a real .env, so this was invisible locally — but CI has no
    // .env, the key was undefined, and two capture suites died on import with
    // `auth/invalid-api-key` before a single test ran. Placeholders keep the
    // import graph loadable without credentials; a real .env still wins, so the
    // live E2E suites keep talking to the real project.
    env: {
      VITE_FIREBASE_API_KEY: localEnv.VITE_FIREBASE_API_KEY || 'test-firebase-api-key',
      VITE_FIREBASE_AUTH_DOMAIN: localEnv.VITE_FIREBASE_AUTH_DOMAIN || 'test.firebaseapp.com',
      VITE_FIREBASE_PROJECT_ID: localEnv.VITE_FIREBASE_PROJECT_ID || 'test-project'
    },
    environment: 'node',
    // .tsx suites opt into jsdom per-file via `// @vitest-environment jsdom`.
    include: ['src/**/*.test.{ts,tsx}', 'scripts/**/*.test.mjs']
  }
})
