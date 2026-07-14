// Postinstall step: keep both Windows native helpers available in a fresh clone
// or git worktree. Their executables are gitignored, so build them locally when
// either is absent. This remains non-fatal so dependency installation can still
// complete without the .NET SDK; the affected native features stay disabled.
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { execSync } from 'node:child_process'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const helpers = ['win-ocr-helper', 'win-automation-helper']
const missing = helpers.filter((name) => !existsSync(join(root, 'resources', name, `${name}.exe`)))

if (process.platform !== 'win32') {
  console.log('[ensure-native-helpers] not Windows - skipping native helpers.')
  process.exit(0)
}
if (missing.length === 0) {
  console.log('[ensure-native-helpers] native helper executables already present - skipping.')
  process.exit(0)
}
try {
  console.log(`[ensure-native-helpers] missing ${missing.join(', ')} - building native helpers...`)
  execSync('npm run build:native-helpers', { stdio: 'inherit', cwd: root })
} catch {
  console.warn(
    '[ensure-native-helpers] could not build native helpers (is the .NET 10 SDK installed?). ' +
      'The app still works, but OCR, screen-reading, and UI automation remain disabled.'
  )
}
process.exit(0)
