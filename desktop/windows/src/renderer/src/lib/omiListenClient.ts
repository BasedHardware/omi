import { auth } from './firebase'
import type { BackendSegment, ListenEvent, ListenSource } from '../../../shared/types'
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
}

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
  cb: OmiListenCallbacks
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
      language: getPreferences().language
    })
  } catch (e) {
    unsub()
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
    stop: (): void => {
      stopped = true
      unsub()
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
      void window.omi.listenStop(sessionId)
    }
  }
}
