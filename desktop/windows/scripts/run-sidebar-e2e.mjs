// Build the app, then run the sidebar shell E2E against the real built main
// process. Hermetic: the spec launches out/main/index.js with a throwaway
// --user-data-dir and OMI_E2E_FAKE_AUTH so the authed shell mounts offline; it
// asserts the collapse-rail layout contract (orb never collides with the
// collapse toggle) and captures the screenshot set (.orb-out/shell-shots) for
// the skeptical review.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=120000', 'e2e/sidebar.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
