// Launch the BUILT app under OMI_SOAK for a long idle run, then verify the
// resulting soak.jsonl. Usage:
//   node scripts/run-soak.mjs [--hours 8] [--minutes N] [--no-build]
//                             [--user-data-dir <dir>]
//
// The app samples memory + listen-byte counters every 60s (src/main/soak.ts). This
// launcher waits the requested wall-clock, stops the app, and runs soak-verify.
// Meant to run in the background (start it, keep building other work) — it does not
// busy-wait. A throwaway --user-data-dir keeps it off the real profile.
import { execFileSync, spawn } from 'node:child_process'
import electronPath from 'electron'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function arg(name, fallback) {
  const i = process.argv.indexOf(name)
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback
}
const hasFlag = (name) => process.argv.includes(name)

const minutes = arg('--minutes')
const runMs =
  minutes !== undefined ? Number(minutes) * 60_000 : Number(arg('--hours', '8')) * 3_600_000
const userDataDir = arg('--user-data-dir', fs.mkdtempSync(path.join(os.tmpdir(), 'omi-soak-')))
const mainEntry = path.join(root, 'out', 'main', 'index.js')

if (!hasFlag('--no-build')) {
  console.log('[soak] building app…')
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}
if (!fs.existsSync(mainEntry)) {
  console.error(`[soak] built main not found (${mainEntry}) — run without --no-build`)
  process.exit(2)
}

console.log(`[soak] launching for ${(runMs / 3_600_000).toFixed(2)}h — userData=${userDataDir}`)
const child = spawn(electronPath, [mainEntry, `--user-data-dir=${userDataDir}`], {
  cwd: root,
  env: { ...process.env, OMI_SOAK: '1', OMI_SKIP_TUNNEL: '1', OMI_AUTOMATION: '0' },
  stdio: 'inherit'
})

let finished = false
async function finish(code) {
  if (finished) return
  finished = true
  try {
    child.kill()
  } catch {
    /* already gone */
  }
  const jsonl = path.join(userDataDir, 'soak.jsonl')
  if (!fs.existsSync(jsonl)) {
    console.error(
      `[soak] no soak.jsonl at ${jsonl} — app may not have booted (OMI_SOAK enabled? registerSoak wired in?)`
    )
    process.exit(2)
  }
  try {
    execFileSync('node', [path.join(root, 'scripts', 'soak-verify.mjs'), '--file', jsonl], {
      stdio: 'inherit',
      cwd: root
    })
    process.exit(code)
  } catch (e) {
    process.exit(e.status ?? 1) // soak-verify's non-zero = FAIL
  }
}

child.on('exit', (code) => {
  if (!finished) {
    console.error(`[soak] app exited early (code ${code}) — verifying whatever was sampled`)
    void finish(1)
  }
})
setTimeout(() => void finish(0), runMs)
