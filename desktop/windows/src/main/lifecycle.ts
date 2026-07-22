// Single source of truth for "the app is really quitting" vs "a window is just
// hiding to the tray". Every close-to-tray decision (main window close, overlay
// close) reads isQuitting(); every real-quit path (tray Quit, Ctrl+Q, the
// app:quit IPC, before-quit) sets it. Consolidated here so the flag can't drift
// between windows.
import { app } from 'electron'

let quitting = false

export function isQuitting(): boolean {
  return quitting
}

/** Mark the app as quitting. Idempotent. */
export function markQuitting(): void {
  quitting = true
}

/** Quit for real: set the flag first so close handlers don't preventDefault. */
export function quitApp(): void {
  markQuitting()
  app.quit()
}

// Any path into shutdown (menu quit, OS logoff, autoUpdater install-on-quit)
// funnels through before-quit; make sure the flag is set even for paths that
// didn't call quitApp().
app.on('before-quit', markQuitting)
