// Postinstall step: on Windows, build win-ocr-helper.exe if it's missing, so a
// fresh clone or git worktree gets working screen-OCR out of the box (the binary is
// gitignored, like .env, so it never travels with the repo). Deliberately a no-op
// off-Windows or when the exe already exists, and NON-FATAL on any failure — it must
// never break `npm install`. If it can't build (e.g. no .NET SDK), the app still
// runs; OCR just stays disabled until `npm run build:ocr-helper` is run.
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const exe = join(root, 'resources', 'win-ocr-helper', 'win-ocr-helper.exe')

if (process.platform !== 'win32') {
  console.log('[ensure-ocr-helper] not Windows — skipping (the OCR helper is Windows-only).')
  process.exit(0)
}
if (existsSync(exe)) {
  console.log('[ensure-ocr-helper] win-ocr-helper.exe already present — skipping.')
  process.exit(0)
}
try {
  console.log('[ensure-ocr-helper] win-ocr-helper.exe missing — building it (needs the .NET SDK)…')
  execSync('npm run build:ocr-helper', { stdio: 'inherit', cwd: root })
} catch {
  console.warn(
    '[ensure-ocr-helper] could NOT build the OCR helper (is the .NET SDK installed?). ' +
      'The app still works; screen-reading stays disabled until you run `npm run build:ocr-helper`.'
  )
}
process.exit(0)
