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
    include: ['src/**/*.test.ts', 'scripts/**/*.test.mjs']
  }
})
