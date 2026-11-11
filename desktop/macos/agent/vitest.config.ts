import { defineConfig } from "vitest/config";

// Codemagic's shared M2 runner can briefly starve CPU, subprocess, and Unix
// socket tests while Vitest runs the full agent suite in parallel. Keep hangs
// bounded while allowing the measured contention-sensitive tests to complete.
export default defineConfig({
  test: {
    testTimeout: 15_000,
    hookTimeout: 20_000,
  },
});
