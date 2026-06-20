// Postinstall step: on Windows, build win-update-helper.exe if it's missing, so a
// fresh clone or git worktree gets the native update-progress dialog out of the box
// (the binary is gitignored, like .env, so it never travels with the repo).
// No-op off-Windows or when the exe already exists, and NON-FATAL on any failure —
// it must never break `npm install`. If it can't build (e.g. no .NET SDK), the app
// still runs; the update progress just falls back to the taskbar bar.
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const exe = join(root, 'resources', 'win-update-helper', 'win-update-helper.exe')

if (process.platform !== 'win32') {
  console.log('[ensure-update-helper] not Windows — skipping (the helper is Windows-only).')
  process.exit(0)
}
if (existsSync(exe)) {
  console.log('[ensure-update-helper] win-update-helper.exe already present — skipping.')
  process.exit(0)
}
try {
  console.log('[ensure-update-helper] win-update-helper.exe missing — building it (needs the .NET SDK)…')
  execSync('npm run build:update-helper', { stdio: 'inherit', cwd: root })
} catch {
  console.warn(
    '[ensure-update-helper] could NOT build the update helper (is the .NET SDK installed?). ' +
      'The app still works; update progress falls back to the taskbar bar until you run `npm run build:update-helper`.'
  )
}
process.exit(0)
