import { defineConfig } from 'vitest/config';
import path from 'path';

const rootDir = import.meta.dirname;

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./vitest.setup.ts'],
    // userEvent typing tests measure 5-8s wall under a loaded runner (full
    // suite + parallel checks); the 5s default timed them out non-deterministically.
    testTimeout: 15000,
  },
  resolve: {
    alias: {
      '@': path.resolve(rootDir, './src'),
    },
  },
});
