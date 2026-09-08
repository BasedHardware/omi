// Build the app, then run the bar E2E against the real built main process.
// Hermetic: the spec launches out/main/index.js with a throwaway --user-data-dir
// and asserts the bar's focus contract, paint-ack reveal, and the hotkey-tap →
// pill (C5) summon; it also captures the screenshot set (.orb-out/bar-shots) for
// the skeptical review.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=120000', 'e2e/bar.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
