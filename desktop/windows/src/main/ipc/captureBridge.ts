import { ipcMain, BrowserWindow, type WebContents } from 'electron'
import type { CaptureCommand, CaptureEvent } from '../../shared/types'

// Bridges the hidden capture window and the UI windows. The capture window owns
// ALL audio + Rewind capture; UI windows are pure UI. Two channels:
//   'omi-capture:cmd'   — a UI window sends a CaptureCommand; main forwards it to
//                         the capture window tagged with the sender's webContents
//                         id (ownerId), so owned events can be routed back.
//   'omi-capture:event' — the capture window emits a CaptureEvent; main accepts
//                         it ONLY from the capture window (spoof guard) and either
//                         routes it to its owner (audio errors, PTT) or broadcasts
//                         it to every non-capture window (live-store, vad-status).
// The main process still owns every listen WebSocket, so audio origin (capture
// window) and transcript destination (any UI window) stay decoupled.

// CaptureEvent types that target a single owning UI window rather than being
// broadcast to all of them. Everything else (live, vad-status,
// capture-window-restarted) fans out to every non-capture window.
const OWNED_EVENT_TYPES = new Set<CaptureEvent['type']>([
  'audio-source-error',
  'ptt-chunk',
  'ptt-drained',
  'ptt-capped',
  'ptt-error',
  'ptt-levels'
])

export function isOwnedCaptureEvent(event: CaptureEvent): boolean {
  return OWNED_EVENT_TYPES.has(event.type)
}

/**
 * Pure routing decision: given an event, the ownerId the capture window tagged it
 * with (if any), and the ids of the candidate (non-capture) windows, return the
 * window ids that should receive it. Owned events go to their owner only (dropped
 * if that window is gone); all others broadcast. Kept pure so it's unit-testable
 * without Electron.
 */
export function routeCaptureEvent(
  event: CaptureEvent,
  ownerId: number | undefined,
  windowIds: number[]
): number[] {
  if (isOwnedCaptureEvent(event)) {
    return ownerId !== undefined && windowIds.includes(ownerId) ? [ownerId] : []
  }
  return windowIds
}

/**
 * Emit a capture event that ORIGINATES in main (e.g. capture-window-restarted)
 * to every UI window, skipping the capture window itself. Used for events the
 * capture window can't send about itself (its own recreation).
 */
export function emitCaptureEventFromMain(event: CaptureEvent, captureWcId: number | null): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (w.isDestroyed() || w.webContents.id === captureWcId) continue
    w.webContents.send('omi-capture:event', event)
  }
}

/**
 * Wire the capture bridge. `getCaptureWc` returns the capture window's
 * webContents (or null before it exists / after teardown) — it's read live on
 * every message so a recreated capture window is picked up automatically.
 */
export function registerCaptureBridge(getCaptureWc: () => WebContents | null): void {
  ipcMain.on('omi-capture:cmd', (e, cmd: CaptureCommand) => {
    const wc = getCaptureWc()
    if (!wc || wc.isDestroyed()) return
    // Forward to the capture window tagged with the sender's id (ownerId) so owned
    // events (audio errors, PTT) route back to it. The capture window's OWN
    // continuous-mic lane also issues audio-start (its omiListenClient runs in this
    // window), so a command from the capture window is forwarded to it too — that's
    // not a loop (a command handler never re-issues the command; audio chunks flow
    // via listenFeed, not commands). AudioSessionHost is idempotent per sessionId.
    wc.send('omi-capture:cmd', { cmd, ownerId: e.sender.id })
  })

  ipcMain.on('omi-capture:event', (e, payload: { event: CaptureEvent; ownerId?: number }) => {
    const wc = getCaptureWc()
    // Spoof guard: web content other than the capture window must not be able to
    // inject capture events (it would let a hostile/XSS'd UI window forge PTT
    // audio or live-store ops into other windows).
    if (!wc || wc.isDestroyed() || e.sender.id !== wc.id) return
    const targets = BrowserWindow.getAllWindows().filter(
      (w) => !w.isDestroyed() && w.webContents.id !== wc.id
    )
    const targetIds = routeCaptureEvent(
      payload.event,
      payload.ownerId,
      targets.map((w) => w.webContents.id)
    )
    for (const w of targets) {
      if (targetIds.includes(w.webContents.id))
        w.webContents.send('omi-capture:event', payload.event)
    }
  })
}
