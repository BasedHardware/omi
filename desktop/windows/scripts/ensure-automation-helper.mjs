// Postinstall step: on Windows, build win-automation-helper.exe if it's missing, so a
// fresh clone, git worktree, or packaged build gets working UI automation out of the box
// (the binary is gitignored, like .env, so it never travels with the repo). Deliberately
// a no-op off-Windows or when the exe already exists, and NON-FATAL on any failure — it
// must never break `npm install`. If it can't build (e.g. no .NET SDK), the app still
// runs; UI automation just stays disabled until `npm run build:automation-helper` is run.
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const exe = join(root, 'resources', 'win-automation-helper', 'win-automation-helper.exe')

if (process.platform !== 'win32') {
  console.log('[ensure-automation-helper] not Windows — skipping (the automation helper is Windows-only).')
  process.exit(0)
}
if (existsSync(exe)) {
  console.log('[ensure-automation-helper] win-automation-helper.exe already present — skipping.')
  process.exit(0)
}
try {
  console.log('[ensure-automation-helper] win-automation-helper.exe missing — building it (needs the .NET SDK)…')
  execSync('npm run build:automation-helper', { stdio: 'inherit', cwd: root })
} catch {
  console.warn(
    '[ensure-automation-helper] could NOT build the automation helper (is the .NET SDK installed?). ' +
      'The app still works; UI automation stays disabled until you run `npm run build:automation-helper`.'
  )
}
process.exit(0)
