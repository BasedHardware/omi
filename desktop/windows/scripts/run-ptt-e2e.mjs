// Run the live PTT E2E suite with the explicit opt-in flag set. The suite itself
// gates on OMI_E2E=1 (process env) so that a refresh token stored in .env can
// never silently turn the hermetic `pnpm test` run into a live network suite.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
execFileSync('node', [path.join(root, 'scripts', 'gen-audio-fixtures.mjs')], {
  stdio: 'inherit',
  cwd: root
})
execFileSync('npx', ['vitest', 'run', 'src/main/ipc/pttTranscribe.e2e.test.ts'], {
  stdio: 'inherit',
  cwd: root,
  shell: true,
  env: { ...process.env, OMI_E2E: '1' }
})
