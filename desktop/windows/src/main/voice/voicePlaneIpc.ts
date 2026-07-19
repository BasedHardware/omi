// Main-process wiring for the voice-plane flight recorder and the
// `resetVoicePlane` command (2026-07-18 voice-plane supervisor).
//
// The recorder is main-resident so bar / main / capture events merge into ONE
// cross-window timeline (each of the day's silent voice failures spanned
// windows). `resetVoicePlane` is the app-restart-equivalent scoped to voice:
// main dumps the evidence, restores any endpoint mute it may hold, and
// broadcasts `voice:planeReset` so every renderer drops and rebuilds its voice
// stack (the main window rebuilds the hub driver; the bar clears its lanes).
// Idempotent and safe at any moment — every step below tolerates a healthy,
// wedged, or mid-turn plane.

import { app, BrowserWindow, ipcMain, type IpcMainEvent } from 'electron'
import path from 'path'
import type { VoiceHubBarState } from '../../shared/types'
import { systemAudioMuteBridge } from '../audio/systemAudioMute'
import { dumpVoiceFlight, initVoiceFlightRecorder, recordVoiceFlight } from './flightRecorder'

const IDLE_HUB_BAR_STATE: VoiceHubBarState = {
  active: false,
  isListening: false,
  isThinking: false,
  isResponseActive: false,
  orbLevel: 0,
  hint: ''
}

/** Which renderer sent an event, from its hash route ('#/bar' → 'bar'). */
function senderLabel(e: IpcMainEvent): string {
  try {
    const url = e.sender.getURL()
    const hash = url.split('#/')[1]
    return hash ? hash.split(/[/?]/)[0] : 'renderer'
  } catch {
    return 'renderer'
  }
}

export function registerVoicePlaneIpc(): void {
  initVoiceFlightRecorder(() => path.join(app.getPath('userData'), 'logs'))

  // Fire-and-forget event append from any renderer. Payloads are re-validated
  // here (type must be a short string; data must be a plain object) because the
  // channel is reachable from every window.
  ipcMain.on('voice:flightRecord', (e, type: unknown, data?: unknown) => {
    if (typeof type !== 'string' || type.length === 0 || type.length > 64) return
    const payload =
      data !== null && typeof data === 'object' && !Array.isArray(data)
        ? (data as Record<string, unknown>)
        : undefined
    recordVoiceFlight(senderLabel(e), type, payload)
  })

  ipcMain.on('voice:resetPlane', (e, trigger: unknown) => {
    resetVoicePlane(typeof trigger === 'string' ? trigger.slice(0, 64) : 'unknown', senderLabel(e))
  })
}

/** Rebuild the entire voice plane. Callable from main directly (bar context
 *  menu) or via the `voice:resetPlane` IPC (bar supervisor). */
export function resetVoicePlane(trigger: string, from = 'main'): void {
  recordVoiceFlight('main', 'reset_voice_plane', { trigger, from })
  // Dump FIRST so the file shows the plane exactly as it was when the reset was
  // commanded (the reset itself then appends to the live ring).
  dumpVoiceFlight(`reset:${trigger}`)
  // Never leave the endpoint muted across a reset — the bridge's restore is
  // unconditional and idempotent (a no-op when it holds no mute).
  void systemAudioMuteBridge.restoreSystemAudio()
  for (const w of BrowserWindow.getAllWindows()) {
    if (w.isDestroyed()) continue
    w.webContents.send('voice:planeReset', { trigger })
    // Force the bar's hub orb to idle DIRECTLY from main: the normal idle
    // projection rides the main window's driver, which is exactly the thing
    // that may be too wedged to emit it. Only the bar listens on this channel.
    w.webContents.send('voiceHub:state', IDLE_HUB_BAR_STATE)
  }
}
