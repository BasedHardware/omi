import { auth } from './firebase'
import { startOmiListen, type OmiListenHandle } from './omiListenClient'
import type { BackendSegment, ListenSource, TranscriptLine } from '../../../shared/types'

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
}

export type TranscriptionHandle = {
  stop: () => void
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

/**
 * Start an Omi v4/listen session for one source. Resolves the handle once the
 * socket connects, or null on an initial failure (connect timeout, fatal WS
 * error, no signed-in user, or quota exhausted before connect). `onLost` fires
 * when a CONNECTED session can no longer continue (quota exhausted or socket
 * dropped) so the caller can surface an error to the user.
 */
async function startWithOmi(
  source: ListenSource,
  cb: TranscriptionCallbacks,
  onLost: (reason: string) => void
): Promise<OmiListenHandle | null> {
  if (!auth.currentUser) return null
  let outcome: 'pending' | 'omi' | 'failed' = 'pending'
  return new Promise<OmiListenHandle | null>((resolve) => {
    let handle: OmiListenHandle | null = null
    const timeout = setTimeout(() => {
      if (outcome !== 'pending') return
      outcome = 'failed'
      try {
        handle?.stop()
      } catch {
        /* ignore */
      }
      resolve(null)
    }, CONNECT_TIMEOUT_MS)

    startOmiListen(source, {
      onConnected: () => {
        if (outcome !== 'pending') return
        outcome = 'omi'
        clearTimeout(timeout)
        cb.onBackend('omi')
        resolve(handle)
      },
      onSegments: (segs) => {
        if (outcome !== 'omi') return
        for (const s of segs) cb.onLine(segmentToLine(s))
      },
      onEvent: (ev) => {
        cb.onEvent?.(ev)
        if (!isQuotaExhaustedEvent(ev)) return
        // Free quota is used up — the cloud STT will never emit transcripts.
        if (outcome === 'pending') {
          // Never connected as the winner yet: treat as an initial failure.
          outcome = 'failed'
          clearTimeout(timeout)
          try {
            handle?.stop()
          } catch {
            /* ignore */
          }
          resolve(null)
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
          outcome = 'failed'
          clearTimeout(timeout)
          try {
            handle?.stop()
          } catch {
            /* ignore */
          }
          console.warn(`[v4/listen ${source}] initial failure:`, err.message)
          resolve(null)
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
    })
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
        }
      })
      .catch((err) => {
        if (outcome !== 'pending') return
        outcome = 'failed'
        clearTimeout(timeout)
        console.warn(`[v4/listen ${source}] start threw:`, err)
        resolve(null)
      })
  })
}

/**
 * Begin transcribing one audio source via Omi v4/listen. Omi is the only
 * transcription backend: if it can't connect, runs out of free quota, or its
 * socket drops mid-session, the session ends and `onError` fires. (There is no
 * Deepgram fallback.)
 */
export async function startTranscription(
  source: ListenSource,
  cb: TranscriptionCallbacks
): Promise<TranscriptionHandle> {
  let active: OmiListenHandle | null = null

  const omi = await startWithOmi(source, cb, (reason) => {
    cb.onError(new Error(`Omi transcription stopped: ${reason}`))
  })

  if (omi) {
    active = omi
  } else {
    cb.onError(
      new Error(
        auth.currentUser
          ? 'Omi transcription unavailable (could not connect)'
          : 'Omi transcription unavailable (not signed in)'
      )
    )
  }

  return {
    stop: (): void => {
      try {
        active?.stop()
      } catch {
        /* ignore */
      }
    }
  }
}
