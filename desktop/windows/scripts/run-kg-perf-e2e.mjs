// Build the app, then run the brain-map performance harness against the real
// built main process. Hermetic: /v3/memories + /v1/knowledge-graph are served from
// a synthetic scale-matched fixture via page.route(), with a catch-all abort — no
// real backend, no real account data. Prints draw-call + fps numbers and drops
// before/after screenshots in .playwright-mcp/brainmap-perf/ for a reviewer.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=180000', 'e2e/knowledge-graph-perf.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
