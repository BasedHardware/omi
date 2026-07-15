// Postinstall step: on Windows, build win-audio-helper.exe if it's missing, so a
// fresh clone or git worktree gets working PTT system-audio muting out of the box
// (the binary is gitignored, like .env, so it never travels with the repo).
// Deliberately a no-op off-Windows or when the exe already exists, and NON-FATAL
// on any failure — it must never break `npm install`. If it can't build (e.g. no
// .NET SDK), the app still runs; PTT just won't mute other apps until
// `npm run build:audio-helper` is run. Mirrors ensure-ocr-helper.mjs.
import { existsSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const exe = join(root, 'resources', 'win-audio-helper', 'win-audio-helper.exe')
const srcDir = join(root, 'src', 'main', 'audio', 'helper')

/** Newest mtime among the helper's sources (Program.cs, the .csproj). */
function newestSourceMtime() {
  return readdirSync(srcDir)
    .filter((f) => f.endsWith('.cs') || f.endsWith('.csproj'))
    .reduce((max, f) => Math.max(max, statSync(join(srcDir, f)).mtimeMs), 0)
}

if (process.platform !== 'win32') {
  console.log('[ensure-audio-helper] not Windows — skipping (the audio helper is Windows-only).')
  process.exit(0)
}
// Rebuild when the exe is missing OR older than its sources. A stale binary is
// worse than a missing one: the bridge's version handshake would flag it, but the
// helper would still answer — with the OLD behavior. (The v1→v2 peak-sampling fix
// is exactly that case: a stale v1 exe silently refuses to mute.)
if (existsSync(exe) && statSync(exe).mtimeMs >= newestSourceMtime()) {
  console.log('[ensure-audio-helper] win-audio-helper.exe is up to date — skipping.')
  process.exit(0)
}
try {
  console.log(
    `[ensure-audio-helper] win-audio-helper.exe ${existsSync(exe) ? 'is stale' : 'is missing'} — building it (needs the .NET SDK)…`
  )
  execSync('npm run build:audio-helper', { stdio: 'inherit', cwd: root })
} catch {
  console.warn(
    '\n' +
      '========================================================================\n' +
      '[ensure-audio-helper] WARNING: win-audio-helper.exe was NOT built.\n' +
      '  Feature DISABLED: A4 PTT system-audio mute/duck (push-to-talk will not\n' +
      "  mute or duck other apps' audio while you speak).\n" +
      '  Likely cause: the .NET SDK is not installed on this machine.\n' +
      '  To enable it: install the .NET SDK, then run: npm run build:audio-helper\n' +
      '========================================================================\n'
  )
}
process.exit(0)
