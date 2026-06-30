// Drives the native Windows update-progress dialog (win-update-helper.exe). The
// helper renders a Task Dialog with a live progress bar; we spawn it on the first
// progress tick and feed it `progress <pct>` / `done` on stdin. Replaces the
// earlier Electron pop-up window — this is a genuine native Windows dialog.
import { spawn, type ChildProcess } from 'child_process'
import { existsSync } from 'fs'
import { resolveUpdateHelperPath } from './resolveHelperPath'

let proc: ChildProcess | null = null
let closingByUs = false
// True once the user closed the dialog themselves (Hide / ✕) — don't re-pop it
// for the rest of this download.
let dismissed = false

/** Show (spawn if needed) the native progress dialog and push the latest percent. */
export function showUpdateProgress(version: string, percent: number): void {
  if (dismissed) return
  if (!proc) {
    const exe = resolveUpdateHelperPath()
    if (!existsSync(exe)) {
      console.warn('[autoUpdate] update-progress helper not found:', exe)
      return
    }
    closingByUs = false
    // NB: no `windowsHide` — it sets CREATE_NO_WINDOW, which suppresses the
    // helper's Task Dialog from appearing. The helper is a WinExe, so there's no
    // console window to hide anyway.
    proc = spawn(exe, [version], { stdio: ['pipe', 'ignore', 'ignore'] })
    proc.on('error', (e) => {
      console.warn('[autoUpdate] progress helper spawn error:', e?.message ?? e)
      proc = null
    })
    proc.on('exit', () => {
      const wasUs = closingByUs
      proc = null
      closingByUs = false
      if (!wasUs) dismissed = true // user dismissed — stay closed this download
    })
  }
  try {
    proc.stdin?.write(`progress ${Math.max(0, Math.min(100, Math.round(percent)))}\n`)
  } catch {
    /* helper gone — ignore */
  }
}

/** Close the native progress dialog (download finished / cancelled / errored). */
export function hideUpdateProgress(): void {
  dismissed = false // reset for the next download
  if (!proc) return
  closingByUs = true
  const p = proc
  proc = null
  try {
    p.stdin?.write('done\n')
  } catch {
    /* ignore */
  }
  // Belt-and-suspenders: ensure it exits even if it didn't honor 'done'.
  setTimeout(() => {
    try {
      if (!p.killed) p.kill()
    } catch {
      /* ignore */
    }
  }, 1500)
}
