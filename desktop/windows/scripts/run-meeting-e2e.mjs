// Build the app, then run the meeting-detection E2E against the real built
// main process. Hermetic: fake Tier1/Tier2 signals via the OMI_E2E hook; real
// YAMNet inference on fixture PCM (no audio devices, no auth, no network).
// Pass --no-build to reuse an existing out/.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=120000', 'e2e/meeting.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
