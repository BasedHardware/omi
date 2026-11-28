// Build the app, then run the Rewind day-scope UI E2E against the real built main
// process. Hermetic: seeds a throwaway SQLite DB + JPEGs via OMI_DB_PATH /
// --user-data-dir, points the embedding indexer at a local stub server (no live
// API, no real credentials), drives the day-scoped Rewind UI, and captures the
// screenshot set into .playwright-mcp/pr3/ for the skeptical review.
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')
const exampleApiKey = readFileSync(path.join(root, '.env.example'), 'utf8')
  .split(/\r?\n/)
  .find((line) => line.startsWith('VITE_FIREBASE_API_KEY='))
  ?.split('=', 2)[1]
const buildEnv = exampleApiKey
  ? { ...process.env, VITE_FIREBASE_API_KEY: process.env.VITE_FIREBASE_API_KEY ?? exampleApiKey }
  : process.env

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], {
    stdio: 'inherit',
    cwd: root,
    env: buildEnv,
    shell: true
  })
}

execFileSync('node', ['--test', '--test-timeout=180000', 'e2e/rewind-dayscope.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
