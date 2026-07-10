import { defineConfig } from 'vitest/config'
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      // Node-side suites import main-process modules whose graph pulls in
      // `electron`, whose real entry needs the native binary. Alias to a stub.
      electron: resolve(__dirname, 'test/electronStub.ts')
    }
  },
  test: {
    environment: 'node',
    // .tsx suites opt into jsdom per-file via `// @vitest-environment jsdom`.
    include: ['src/**/*.test.{ts,tsx}', 'scripts/**/*.test.mjs']
  }
})
