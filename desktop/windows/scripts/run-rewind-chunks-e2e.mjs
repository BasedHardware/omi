// Build the app, then run the Rewind video-chunk E2E against the real built
// renderer. Hermetic: no network, no credentials — it generates its own frames
// and drives the production encoder/decoder through WebCodecs.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  // ensure-env first: without a .env the renderer bundle throws
  // `auth/invalid-api-key` while Firebase initialises, which kills module
  // evaluation before the E2E hooks are installed and leaves the spec waiting
  // for a window that will never have them.
  execFileSync('node', ['scripts/ensure-env.mjs'], { stdio: 'inherit', cwd: root })
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=300000', 'e2e/rewind-chunks.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
