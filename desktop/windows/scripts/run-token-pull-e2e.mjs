// Build the app, then run the token-PULL channel E2E against the real built main
// process. Hermetic: fake auth (OMI_E2E_FAKE_AUTH), an isolated throwaway userData
// dir, no real backend, no real account. Proves the main<->renderer freshness-pull
// round-trip transports over the real Electron IPC boundary (both sides real code).
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=180000', 'e2e/token-pull.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
