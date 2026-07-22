// Build the app, then run the ConversationDetail (PR6) E2E against the real
// built main process. Hermetic: every /v1/** call is served from fixtures via
// page.route(), with a catch-all that aborts anything unmatched — it never
// touches a real backend or real account data. Screenshots land in
// .playwright-mcp/pr6/ for an independent reviewer.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=180000', 'e2e/conversation-detail.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
