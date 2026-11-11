import { defineConfig, type Plugin } from 'vitest/config'
import { dirname, resolve } from 'path'

// Unit tests never inherit service endpoints or Firebase identity from a developer .env.
const testApiBase = 'http://127.0.0.1:9'
process.env.VITE_OMI_API_BASE = testApiBase
process.env.VITE_OMI_DESKTOP_API_BASE = testApiBase

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
      electron: resolve(__dirname, 'test/electronStub.ts'),
      '@omi/note-shared': resolve(__dirname, '../../web/packages/note-shared')
    }
  },
  test: {
    setupFiles: [resolve(__dirname, 'test/hermeticSetup.ts')],
    env: {
      VITE_OMI_API_BASE: testApiBase,
      VITE_OMI_DESKTOP_API_BASE: testApiBase,
      VITE_FIREBASE_API_KEY: 'test-firebase-api-key',
      VITE_FIREBASE_AUTH_DOMAIN: 'test.firebaseapp.com',
      VITE_FIREBASE_PROJECT_ID: 'test-project'
    },
    environment: 'node',
    // .tsx suites opt into jsdom per-file via `// @vitest-environment jsdom`.
    include: ['src/**/*.test.{ts,tsx}', 'scripts/**/*.test.mjs']
  }
})
