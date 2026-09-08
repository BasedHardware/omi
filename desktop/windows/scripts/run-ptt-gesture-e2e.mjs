// Build the app, then run the PTT summon-gesture E2E against the real built
// main process. Hermetic: the spec launches out/main/index.js with a throwaway
// --user-data-dir and reproduces the blind-sampler tap-storm field bug via the
// __omiE2E.barSummonFire hook (no global hotkey, no audio, no network).
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=120000', 'e2e/ptt-gesture.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
