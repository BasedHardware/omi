import { auth } from './firebase'
import type { BackendSegment, ListenEvent, ListenMode, ListenSource } from '../../../shared/types'
import { getPreferences } from './preferences'

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
  /** PTT only: stop the mic capture (after a short tail) and tell the backend to
   *  flush + finalize so the trailing segment lands promptly. The socket stays open
   *  to RECEIVE that segment — but no further audio is sent, so speech after the
   *  hold is released can never leak into the transcript. No-op for conversation
   *  sessions. */
  finalize: () => void
}

// After finalize() we keep capturing for one more ScriptProcessor window before
// cutting the mic: the processor delivers audio in 4096-sample (~256ms) buffers,
// so stopping instantly would drop the in-flight partial buffer and clip the last
// syllable of short words ("one", "hey"). Speech beyond this tail is discarded —
// the released key is the source of truth.
const FINALIZE_TAIL_MS = 300

let nextSessionId = 1

async function getSystemAudioStream(): Promise<MediaStream> {
  let display: MediaStream
  try {
    display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
  } catch (e) {
    const err = e as Error
    if (/not supported/i.test(err.message)) {
      throw new Error(
        'System-audio capture handler not active. Fully restart the app (stop and rerun `npm run dev`) so the main process reloads.'
      )
    }
    throw e
  }
  const audioTracks = display.getAudioTracks()
  display.getVideoTracks().forEach((t) => t.stop())
  if (audioTracks.length === 0) {
    throw new Error('Windows returned no system-audio (loopback) track.')
  }
  return new MediaStream(audioTracks)
}

/**
 * Open a v4/listen session for one audio source. The renderer captures PCM
 * with AudioContext, then forwards each
 * 4096-sample buffer to the main process as Int16. The main process owns the
 * WebSocket (needed to set the Authorization header).
 */
export async function startOmiListen(
  source: ListenSource,
  cb: OmiListenCallbacks,
  mode: ListenMode = 'conversation'
): Promise<OmiListenHandle> {
  const user = auth.currentUser
  if (!user) throw new Error('Omi v4/listen requires sign-in.')
  const token = await user.getIdToken()
  const sessionId = `omi-listen-${Date.now()}-${nextSessionId++}`

  const stream =
    source === 'mic'
      ? await navigator.mediaDevices.getUserMedia({ audio: true })
      : await getSystemAudioStream()

  const audioCtx = new AudioContext({ sampleRate: 16000 })
  const node = audioCtx.createMediaStreamSource(stream)
  const processor = audioCtx.createScriptProcessor(4096, 1, 1)
  node.connect(processor)

  let stopped = false
  let connected = false
  let finalizing = false
  let captureStopped = false

  // Tear down just the audio-capture graph (mic stream, processor, context) —
  // idempotent, and independent of the WS session so finalize() can cut the mic
  // while the socket stays open for the trailing transcript.
  const stopCapture = (): void => {
    if (captureStopped) return
    captureStopped = true
    try {
      processor.disconnect()
    } catch {
      /* ignore */
    }
    try {
      node.disconnect()
    } catch {
      /* ignore */
    }
    try {
      stream.getTracks().forEach((t) => t.stop())
    } catch {
      /* ignore */
    }
    try {
      void audioCtx.close()
    } catch {
      /* ignore */
    }
  }

  const unsub = window.omi.onListenMessage((msg) => {
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

  try {
    await window.omi.listenStart({
      sessionId,
      source,
      token,
      language: getPreferences().language,
      mode
    })
  } catch (e) {
    unsub()
    stopCapture()
    throw e
  }

  processor.onaudioprocess = (e): void => {
    if (stopped) return
    const f32 = e.inputBuffer.getChannelData(0)
    const i16 = new Int16Array(f32.length)
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]))
      i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    // Transfer the underlying buffer to keep IPC cheap.
    window.omi.listenFeed(sessionId, i16.buffer)
  }
  processor.connect(audioCtx.destination)

  return {
    finalize: (): void => {
      if (stopped || finalizing) return
      finalizing = true
      // One more processor window of tail so the final syllable's in-flight partial
      // buffer still ships, then the mic goes dead and the backend is told to flush.
      // The IPC channel preserves ordering, so the tail audio lands before the
      // finalize frame.
      setTimeout(() => {
        stopCapture()
        if (!stopped) window.omi.listenFinalize(sessionId)
      }, FINALIZE_TAIL_MS)
    },
    stop: (): void => {
      stopped = true
      unsub()
      stopCapture()
      void window.omi.listenStop(sessionId)
    }
  }
}
