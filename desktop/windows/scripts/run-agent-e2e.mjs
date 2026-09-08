// Run the live coding-agent (ACP) E2E suite with the explicit opt-in flag set.
// The suite gates on OMI_E2E=1 (process env) so it can never run as part of the
// hermetic `pnpm test`. Same gating shape as scripts/run-live-e2e.mjs (PTT),
// minus the audio-fixture step, which the agent suite has no use for.
//
//   node scripts/run-agent-e2e.mjs <vitest-test-file>
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const testFile = process.argv[2]
if (!testFile) {
  console.error('usage: node scripts/run-agent-e2e.mjs <vitest-test-file>')
  process.exit(1)
}

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
execFileSync('npx', ['vitest', 'run', testFile], {
  stdio: 'inherit',
  cwd: root,
  shell: true,
  env: { ...process.env, OMI_E2E: '1' }
})
