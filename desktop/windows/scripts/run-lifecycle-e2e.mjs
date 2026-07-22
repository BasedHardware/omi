// Build the app, then run the lifecycle E2E against the real built main process.
// Hermetic: the spec launches out/main/index.js with a throwaway --user-data-dir
// and asserts only main-process facts (renderer/Firebase errors are ignored).
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

// Build main + preload + renderer so out/main/index.js is current (skip with
// --no-build to reuse an existing out/ from a prior build).
if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

// node:test runner. --test-timeout guards against a wedged launch.
execFileSync('node', ['--test', '--test-timeout=60000', 'e2e/lifecycle.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
