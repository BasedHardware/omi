// Run the live conversation-sync E2E suite with the explicit opt-in flag set.
// The suite gates on OMI_E2E=1 (process env) so a refresh token stored in .env
// can never silently turn the hermetic `pnpm test` run into a live suite.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
execFileSync('node', [path.join(root, 'scripts', 'gen-audio-fixtures.mjs')], {
  stdio: 'inherit',
  cwd: root
})
execFileSync('npx', ['vitest', 'run', 'src/renderer/src/lib/sync/convSync.e2e.test.ts'], {
  stdio: 'inherit',
  cwd: root,
  shell: true,
  env: { ...process.env, OMI_E2E: '1' }
})
