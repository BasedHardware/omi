// Build the app, then run the Rewind day-scope UI E2E against the real built main
// process. Hermetic: seeds a throwaway SQLite DB + JPEGs via OMI_DB_PATH /
// --user-data-dir, points the embedding indexer at a local stub server (no live
// API, no real credentials), drives the day-scoped Rewind UI, and captures the
// screenshot set into .playwright-mcp/pr3/ for the skeptical review.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=180000', 'e2e/rewind-dayscope.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
