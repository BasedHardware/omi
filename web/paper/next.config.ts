import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Pin the file-tracing root to this app dir. Next 15+ otherwise infers the
  // workspace root from the repo-root lockfile (this repo has no monorepo
  // tooling; web/* are independent apps) and traces files from there.
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
};

export default nextConfig;
