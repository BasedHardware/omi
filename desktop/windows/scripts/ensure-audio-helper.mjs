// Postinstall step: on Windows, build win-audio-helper.exe if it's missing, so a
// fresh clone or git worktree gets working PTT system-audio muting out of the box
// (the binary is gitignored, like .env, so it never travels with the repo).
// Deliberately a no-op off-Windows or when the exe already exists, and NON-FATAL
// on any failure — it must never break `npm install`. If it can't build (e.g. no
// .NET SDK), the app still runs; PTT just won't mute other apps until
// `npm run build:audio-helper` is run. Mirrors ensure-ocr-helper.mjs.
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const exe = join(root, 'resources', 'win-audio-helper', 'win-audio-helper.exe')

if (process.platform !== 'win32') {
  console.log('[ensure-audio-helper] not Windows — skipping (the audio helper is Windows-only).')
  process.exit(0)
}
if (existsSync(exe)) {
  console.log('[ensure-audio-helper] win-audio-helper.exe already present — skipping.')
  process.exit(0)
}
try {
  console.log(
    '[ensure-audio-helper] win-audio-helper.exe missing — building it (needs the .NET SDK)…'
  )
  execSync('npm run build:audio-helper', { stdio: 'inherit', cwd: root })
} catch {
  console.warn(
    '[ensure-audio-helper] could NOT build the audio helper (is the .NET SDK installed?). ' +
      'The app still works; PTT system-audio muting stays disabled until you run `npm run build:audio-helper`.'
  )
}
process.exit(0)
