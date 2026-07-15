// Build the app, then run the Rewind semantic-search E2E against the real built
// main process. Hermetic: the Gemini proxy is a local stub the app is pointed at
// via the relayed session's desktopApiBase, so no live API and no real
// credentials are involved.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=120000', 'e2e/rewind-semantic.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
