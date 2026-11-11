// Run a live E2E suite (PTT / conversation sync) with the explicit opt-in flag
// set. The suites gate on OMI_E2E=1 (process env) so a refresh token stored in
// .env can never silently turn the hermetic `pnpm test` run into a live network
// suite. Audio fixtures are (re)generated first when missing.
//
//   node scripts/run-live-e2e.mjs <vitest-test-file>
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const testFile = process.argv[2]
if (!testFile) {
  console.error('usage: node scripts/run-live-e2e.mjs <vitest-test-file>')
  process.exit(1)
}

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
execFileSync('node', [path.join(root, 'scripts', 'gen-audio-fixtures.mjs')], {
  stdio: 'inherit',
  cwd: root
})
execFileSync('npx', ['vitest', 'run', testFile], {
  stdio: 'inherit',
  cwd: root,
  shell: true,
  env: { ...process.env, OMI_E2E: '1' }
})
