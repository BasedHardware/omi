import { auth } from './firebase'
import { startOmiListen, type OmiListenHandle } from './omiListenClient'
import type {
  BackendSegment,
  ListenMode,
  ListenSource,
  TranscriptLine
} from '../../../shared/types'

/** The session modes this client can drive ('ptt' rides lib/ptt/ instead). */
export type TranscriptionMode = Extract<ListenMode, 'conversation' | 'transcribe'>

// Conversation (/v4/listen) connects fast; a tight timeout surfaces failures
// quickly. (Push-to-talk does NOT ride this client — see lib/ptt/, whose stream
// lane is opportunistic and needs no connect timeout at all.)
const CONNECT_TIMEOUT_MS = 3000

export type TranscriptionCallbacks = {
  /** Fires every time a new finalized line is ready (a v4/listen segment). */
  onLine: (line: TranscriptLine) => void
  /** Reserved for in-progress interim text. The Omi v4/listen path emits only
   *  finalized segments, so this currently never fires; kept so callers that
   *  render interim text don't need to change. */
  onInterim: (text: string) => void
  /** Fires once when the session connects. Always 'omi' (the only backend). */
  onBackend: (backend: 'omi') => void
  /** Fires when transcription can't start or can't continue: connect failure,
   *  quota exhausted, or the socket dropped. The session is over when this fires. */
  onError: (err: Error) => void
  /** Fires for every non-segment backend event (e.g. `memory_creating`). Optional;
   *  quota events are still handled internally regardless. */
  onEvent?: (event: { type: string; raw: Record<string, unknown> }) => void
  /** Fires with each RAW segment batch before line mapping. Screen sessions use
   *  this to retain the from-segments fields (start/end/is_user/speaker_id/…)
   *  that segmentToLine discards — see lib/sync/segmentRetention.ts. */
  onSegments?: (segments: BackendSegment[]) => void
}

export type TranscriptionHandle = {
  stop: () => void
  /** Flush the trailing segment of a 'transcribe' session now (no-op otherwise). */
  finalize: () => void
}

function segmentToLine(seg: BackendSegment): TranscriptLine {
  const speaker = seg.is_user
    ? 'You'
    : seg.speaker
      ? seg.speaker
      : typeof seg.speaker_id === 'number'
        ? `Speaker ${seg.speaker_id}`
        : undefined
  return { id: seg.id, speaker, text: seg.text }
}

/**
 * Omi cloud signals an exhausted free quota two ways: a typed
 * `freemium_threshold_reached` event sent right after connect, and/or a
 * `1008 trial_expired` WebSocket close. Either way the cloud STT will never emit
 * transcripts, so the session has effectively ended.
 */
function isQuotaExhaustedEvent(ev: { type: string; raw: Record<string, unknown> }): boolean {
  if (ev.type !== 'freemium_threshold_reached') return false
  // Only treat the quota as gone when it's actually depleted, not on an
  // early-warning variant of the same event. Missing field = exhausted (fail safe).
  const remaining = ev.raw.remaining_seconds
  return typeof remaining !== 'number' || remaining <= 0
}
/** Whether a message indicates the account's cloud STT entitlement is exhausted
 *  (quota used up / trial expired / policy-violation 1008). Exported so callers
 *  outside this module (e.g. capture/liveRescue.ts's reconnect-worthiness check)
 *  don't re-derive this classification with their own regex. */
export function isQuotaExhaustedMessage(message: string): boolean {
  return /quota|1008|trial_expired/i.test(message)
}
function isTrialExpiredError(err: Error): boolean {
  return /\(1008\)/.test(err.message) || /trial_expired/i.test(err.message)
}
// A connected-then-closed event that means the account isn't entitled to cloud
// STT (free trial/quota used up): WS policy-violation 1008, or a backend reason
// naming the quota. Distinguishes this from a generic network drop so the user
// gets an actionable message instead of a bare "closed (1008)".
function isQuotaClose(code: number, reason: string): boolean {
  return code === 1008 || /trial_expired|freemium|quota/i.test(reason)
}
const QUOTA_MESSAGE =
  'free Omi transcription quota is used up (1008) — add an Omi subscription or sign in with an entitled account to keep transcribing'

type OmiStartOutcome = {
  handle: OmiListenHandle | null
  error: Error | null
}

function startupAbortError(): Error {
  const error = new Error('Transcription startup cancelled')
  error.name = 'AbortError'
  return error
}

/** Start one Omi lane and return its handle or the exact startup failure. */
async function startWithOmi(
  source: ListenSource,
  cb: TranscriptionCallbacks,
  onLost: (reason: string) => void,
  mode: TranscriptionMode,
  clientConversationId?: string,
  signal?: AbortSignal
): Promise<OmiStartOutcome> {
  if (!auth.currentUser) {
    return {
      handle: null,
      error: new Error('Omi transcription unavailable (not signed in)')
    }
  }
  return new Promise<OmiStartOutcome>((resolve) => {
    let outcome: 'pending' | 'omi' | 'failed' = 'pending'
    let handle: OmiListenHandle | null = null
    let readySignaled = false
    let timeout: ReturnType<typeof setTimeout> | null = null

    const stopHandle = (): void => {
      try {
        handle?.stop()
      } catch {
        /* ignore */
      }
    }
    const cleanupStartup = (): void => {
      if (timeout) clearTimeout(timeout)
      timeout = null
      signal?.removeEventListener('abort', onAbort)
    }
    const fail = (error: Error): void => {
      if (outcome !== 'pending') return
      outcome = 'failed'
      cleanupStartup()
      stopHandle()
      resolve({ handle: null, error })
    }
    const maybeSucceed = (): void => {
      if (outcome !== 'pending' || !readySignaled || !handle) return
      outcome = 'omi'
      cleanupStartup()
      cb.onBackend('omi')
      resolve({ handle, error: null })
    }
    const onAbort = (): void => fail(startupAbortError())

    if (signal?.aborted) {
      onAbort()
      return
    }
    signal?.addEventListener('abort', onAbort, { once: true })
    timeout = setTimeout(() => {
      const error = new Error('Omi transcription unavailable (connection or audio timed out)')
      error.name = 'TimeoutError'
      fail(error)
    }, CONNECT_TIMEOUT_MS)

    startOmiListen(
      source,
      {
        onConnected: () => {
          readySignaled = true
          maybeSucceed()
        },
        onSegments: (segs) => {
          if (outcome !== 'omi') return
          cb.onSegments?.(segs)
          for (const s of segs) cb.onLine(segmentToLine(s))
        },
        onEvent: (ev) => {
          cb.onEvent?.(ev)
          if (!isQuotaExhaustedEvent(ev)) return
          // Free quota is used up — the cloud STT will never emit transcripts.
          if (outcome === 'pending') {
            // Never connected as the winner yet: treat as an initial failure.
            fail(new Error(QUOTA_MESSAGE))
          } else if (outcome === 'omi') {
            // Already connected and committed: tell the caller the session is over.
            onLost('Omi free quota exhausted')
          }
        },
        onClosed: (code, reason) => {
          // The Omi socket dropped AFTER connecting (abnormal 1005/1006, clean
          // 1000, etc.). Omi will emit no more transcripts, so end the session.
          // (Pre-connect closes arrive via onError and drive the initial failure.)
          if (outcome !== 'omi') return
          onLost(
            isQuotaClose(code, reason)
              ? QUOTA_MESSAGE
              : `Omi /v4/listen closed (${code})${reason ? ` ${reason}` : ''}`
          )
        },
        onError: (err, fatal) => {
          if (outcome === 'pending' && fatal) {
            console.warn(`[v4/listen ${source}] initial failure:`, err.message)
            fail(err)
            return
          }
          // Only surface post-connect errors when Omi actually connected.
          if (outcome === 'omi') {
            // Quota backstop: a 1008 'trial_expired' close (in case the typed
            // event didn't arrive first). End the session rather than erroring twice.
            if (isTrialExpiredError(err)) {
              onLost(QUOTA_MESSAGE)
              return
            }
            cb.onError(err)
          }
        }
      },
      mode,
      clientConversationId
    )
      .then((h) => {
        // startOmiListen resolves as soon as the WS is *created* — long before
        // it reaches OPEN (~150ms+ away). At that point `outcome` is still
        // 'pending', so we keep the handle and let onConnected/timeout decide.
        // Only tear down if we've ALREADY failed; closing here on a still-pending
        // outcome aborts the handshake mid-connect (ws code 1006).
        if (outcome === 'failed') {
          try {
            h.stop()
          } catch {
            /* ignore */
          }
        } else {
          handle = h
          maybeSucceed()
        }
      })
      .catch((err) => {
        if (outcome !== 'pending') return
        console.warn(`[v4/listen ${source}] start threw:`, err)
        fail(err instanceof Error ? err : new Error(String(err)))
      })
  })
}

/**
 * Begin transcribing one audio source.
 *
 * - mode 'conversation' (default): Omi `/v4/listen`, the full conversation
 *   pipeline with per-uid server-side state — used by continuous MIC-ONLY
 *   recording (one socket, so the backend's user-global pointer is safe).
 * - mode 'transcribe': `/v2/voice-message/transcribe-stream`, transcription-only
 *   — used for BOTH screen-session lanes so no server conversation exists until
 *   the client posts from-segments on stop (see lib/sync/).
 *
 * Push-to-talk does NOT ride this client; it lives in `lib/ptt/`. Omi is the
 * only transcription backend: if it can't connect, runs out of free quota, or
 * its socket drops mid-session, the session ends and `onError` fires. (There is
 * no Deepgram fallback.)
 */
export async function startTranscription(
  source: ListenSource,
  cb: TranscriptionCallbacks,
  mode: TranscriptionMode = 'conversation',
  clientConversationId?: string,
  signal?: AbortSignal
): Promise<TranscriptionHandle> {
  let active: OmiListenHandle | null = null

  const startup = await startWithOmi(
    source,
    cb,
    (reason) => {
      cb.onError(new Error(`Omi transcription stopped: ${reason}`))
    },
    mode,
    clientConversationId,
    signal
  )

  if (!startup.handle) {
    const error =
      startup.error ??
      new Error('Omi transcription unavailable (could not connect or acquire audio)')
    cb.onError(error)
    throw error
  }
  active = startup.handle

  return {
    stop: (): void => {
      try {
        active?.stop()
      } catch {
        /* ignore */
      }
    },
    finalize: (): void => {
      try {
        active?.finalize()
      } catch {
        /* ignore */
      }
    }
  }
}
