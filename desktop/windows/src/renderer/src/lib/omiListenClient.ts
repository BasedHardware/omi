import { auth } from './firebase'
import type { BackendSegment, ListenEvent, ListenMode, ListenSource } from '../../../shared/types'
import { getPreferences } from './preferences'
import { getWindowsDeviceIdHash } from './clientDevice'

export type OmiListenCallbacks = {
  /** Fires once when the v4/listen WS reaches OPEN. */
  onConnected: () => void
  /** Fires for each batch of finalized segments. */
  onSegments: (segments: BackendSegment[]) => void
  /** Fires for type-tagged status events; renderer just logs. */
  onEvent: (event: ListenEvent) => void
  /** Fires for errors. `fatal` means the session is dead. */
  onError: (err: Error, fatal: boolean) => void
  /**
   * Fires when the WS closes AFTER it had connected (any code — clean 1000,
   * quota 1008, or abnormal 1005/1006). The Omi socket is dead, so no more
   * transcripts will arrive; the caller should fall back to keep recording.
   * `reason` is the backend's close text (e.g. `trial_expired`) — needed to tell
   * a quota/entitlement close apart from a generic drop. Pre-connect closes come
   * through `onError(_, fatal=true)` instead.
   */
  onClosed: (code: number, reason: string) => void
}

export type OmiListenHandle = {
  stop: () => void
  /** Ask a transcribe-stream session ('transcribe' mode) to flush its trailing
   * segment now instead of waiting out silence. No-op for 'conversation'
   * sessions and for lanes that never reached OPEN. */
  finalize: () => void
}

let nextSessionId = 1

/**
 * Open a v4/listen session for one audio source. The main process owns the
 * WebSocket (needed to set the Authorization header) and, since Phase 2, the
 * hidden capture window owns the actual audio capture: this client opens the
 * session and OWNS the transcript flow in the CALLING window (byte-identical to
 * before), but the mic/system stream is acquired + fed remotely — we send an
 * `audio-start` command and the capture window's AudioSessionHost runs the
 * pipeline → VAD gate → listenFeed(sessionId). A source (mic/loopback) failure
 * comes back as a routed `audio-source-error` for this sessionId, surfaced here
 * as a fatal error (same shape as the old in-window capture failure).
 */
export async function startOmiListen(
  source: ListenSource,
  cb: OmiListenCallbacks,
  mode: Extract<ListenMode, 'conversation' | 'transcribe'> = 'conversation',
  clientConversationId?: string
): Promise<OmiListenHandle> {
  const user = auth.currentUser
  if (!user) throw new Error('Omi v4/listen requires sign-in.')
  const token = await user.getIdToken()
  const deviceIdHash = await getWindowsDeviceIdHash()
  const sessionId = `omi-listen-${Date.now()}-${nextSessionId++}`

  let stopped = false
  let connected = false

  const unsubMsg = window.omi.onListenMessage((msg) => {
    if (msg.sessionId !== sessionId) return
    if (msg.kind === 'connected') {
      connected = true
      cb.onConnected()
    } else if (msg.kind === 'segments') {
      cb.onSegments(msg.segments)
    } else if (msg.kind === 'event') {
      cb.onEvent(msg.event)
    } else if (msg.kind === 'error') {
      cb.onError(new Error(msg.message), msg.fatal)
    } else if (msg.kind === 'closed') {
      if (stopped) return
      if (connected) {
        // Connected then dropped (clean, quota, or abnormal) → let the caller
        // end the session and surface an error. Pass the reason so a 1008
        // entitlement/quota close can be reported as such, not a bare code.
        cb.onClosed(msg.code, msg.reason)
      } else {
        // Never connected → an initial failure; surface as fatal so the caller
        // reports that transcription couldn't start.
        cb.onError(new Error(`v4/listen closed (${msg.code}) ${msg.reason}`.trim()), true)
      }
    }
  })

  // The audio stream now lives in the capture window. A failure to acquire it (a
  // dead/blocked mic, no loopback track) arrives as a routed audio-source-error
  // for our sessionId — surface it as a fatal source failure.
  const unsubCapture = window.omi.onCaptureEvent((ev) => {
    if (stopped) return
    // The capture window crashed and respawned: its session map is empty, so the
    // still-open WebSocket would silently starve (frozen transcript, no error).
    // Re-issue audio-start — AudioSessionHost re-acquires the source and resumes
    // feeding this session. One seam covers every startOmiListen consumer.
    if (ev.type === 'capture-window-restarted') {
      window.omi.captureCommand({ type: 'audio-start', sessionId, source })
      return
    }
    if (ev.type !== 'audio-source-error' || ev.sessionId !== sessionId) return
    cb.onError(new Error(ev.message || 'audio source failed'), true)
  })

  try {
    await window.omi.listenStart({
      sessionId,
      source,
      token,
      deviceIdHash,
      language: getPreferences().language,
      mode,
      clientConversationId
    })
  } catch (e) {
    unsubMsg()
    unsubCapture()
    throw e
  }

  // Ask the capture window to acquire this source and stream it (VAD-gated) into
  // the session we just opened.
  window.omi.captureCommand({ type: 'audio-start', sessionId, source })

  return {
    stop: (): void => {
      stopped = true
      unsubMsg()
      unsubCapture()
      window.omi.captureCommand({ type: 'audio-stop', sessionId })
      void window.omi.listenStop(sessionId)
    },
    finalize: (): void => {
      window.omi.listenFinalize(sessionId)
    }
  }
}
