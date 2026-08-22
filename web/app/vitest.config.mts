import { defineConfig } from 'vitest/config';
import path from 'path';

const rootDir = import.meta.dirname;

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./vitest.setup.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(rootDir, './src'),
    },
  },
});
