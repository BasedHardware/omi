// Build the app, then run the cold-start cache-first E2E against the real built
// main process. Hermetic: /v3/memories is served from fixtures (launch 1) or
// aborted (launch 2) via page.route(); it never touches a real backend or real
// account data. Proves the per-uid persistentCache mechanism end to end — the
// Memories page renders from its persisted snapshot across an app restart with the
// network down. Screenshots land in .playwright-mcp/cold-start/ for a reviewer.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=180000', 'e2e/cold-start-cache.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
