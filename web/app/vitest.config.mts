import { defineConfig } from 'vitest/config';
import path from 'path';

const rootDir = import.meta.dirname;

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    // `scripts/` holds the moonshine smoke test, which imports `bun:test` and
    // is run by `bun test`. Vitest owns the component and lib suites under
    // `src/`; each runner keeps to its own files.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@': path.resolve(rootDir, './src'),
    },
  },
});
