// Build the app, then run the failure-UX E2E against the real built main process +
// preload bridge (the wiring the jsdom unit tests mock away). Hermetic: throwaway
// --user-data-dir, fake auth, no network.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=90000', 'e2e/failure-ux.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
