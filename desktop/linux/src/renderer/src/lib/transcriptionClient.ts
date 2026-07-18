import { auth } from './firebase'
import { startOmiListen, type OmiListenHandle } from './omiListenClient'
import {
  getVoiceprint,
  labelForSpeaker,
  enrollSpeaker,
  reAnchorIfEnrolled
} from './voiceprint'
import type { BackendSegment, ListenSource, TranscriptLine } from '../../../shared/types'

const CONNECT_TIMEOUT_MS = 3000

export type TranscriptionCallbacks = {
  /** Fires every time a new finalized line is ready (a v4/listen segment). */
  onLine: (line: TranscriptLine) => void
  /** Reserved for in-progress interim text. The Omi v4/listen path emits only
   *  finalized segments, so this currently never fires; kept so callers that
   *  render interim text don't need to change. */
  onInterim: (text: string) => void
  /** Fires once when the session connects. 'omi' or 'deepgram'. */
  onBackend: (backend: 'omi' | 'deepgram') => void
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
  // If Deepgram diarization gave us a speaker cluster, resolve it against the
  // enrolled voiceprint so Omi knows which voice is "You".
  if (typeof seg.speaker_id === 'number') {
    const vp = getVoiceprint()
    // Auto-enroll on first observed utterance if the user hasn't enrolled yet:
    // the first speaker we hear is treated as the user.
    if (!vp.enrolled) {
      enrollSpeaker(seg.speaker_id)
    } else {
      // Re-anchor the enrolled cluster to whatever the user actually produced
      // this session (cluster ids are per-session on nova-2).
      reAnchorIfEnrolled(seg.speaker_id)
    }
    const { speaker, isUser } = labelForSpeaker(seg.speaker_id)
    return { id: seg.id, speaker, text: seg.text, isUser }
  }

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
  const remaining = ev.raw.remaining_seconds
  return typeof remaining !== 'number' || remaining <= 0
}
function isTrialExpiredError(err: Error): boolean {
  return /\(1008\)/.test(err.message) || /trial_expired/i.test(err.message)
}
function isQuotaClose(code: number, reason: string): boolean {
  return code === 1008 || /trial_expired|freemium|quota/i.test(reason)
}
const QUOTA_MESSAGE =
  'free Omi transcription quota is used up (1008) — add an Omi subscription or sign in with an entitled account to keep transcribing'

/**
 * Start a transcription session using Omi v4/listen.
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
      try { handle?.stop() } catch { /* ignore */ }
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
        if (outcome === 'pending') {
          outcome = 'failed'
          clearTimeout(timeout)
          try { handle?.stop() } catch { /* ignore */ }
          resolve(null)
        } else if (outcome === 'omi') {
          onLost('Omi free quota exhausted')
        }
      },
      onClosed: (code, reason) => {
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
          try { handle?.stop() } catch { /* ignore */ }
          console.warn(`[v4/listen ${source}] initial failure:`, err.message)
          resolve(null)
          return
        }
        if (outcome === 'omi') {
          if (isTrialExpiredError(err)) {
            onLost(QUOTA_MESSAGE)
            return
          }
          cb.onError(err)
        }
      }
    })
      .then((h) => {
        if (outcome === 'failed') {
          try { h.stop() } catch { /* ignore */ }
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
 * Start a transcription session using Deepgram.
 * Deepgram uses its own API key (not Firebase auth), so it works even if not signed in.
 */
async function startWithDeepgram(
  source: ListenSource,
  cb: TranscriptionCallbacks,
  onLost: (reason: string) => void
): Promise<OmiListenHandle | null> {
  let outcome: 'pending' | 'deepgram' | 'failed' = 'pending'
  return new Promise<OmiListenHandle | null>((resolve) => {
    let handle: OmiListenHandle | null = null
    const timeout = setTimeout(() => {
      if (outcome !== 'pending') return
      outcome = 'failed'
      try { handle?.stop() } catch { /* ignore */ }
      resolve(null)
    }, CONNECT_TIMEOUT_MS)

    // Deepgram uses its own API key, not Firebase auth token
    const fakeToken = 'deepgram-api-key'

    startOmiListen(
      source,
      {
        onConnected: () => {
          if (outcome !== 'pending') return
          outcome = 'deepgram'
          clearTimeout(timeout)
          cb.onBackend('deepgram')
          resolve(handle)
        },
        onSegments: (segs) => {
          if (outcome !== 'deepgram') return
          for (const s of segs) cb.onLine(segmentToLine(s))
        },
        onEvent: (ev) => {
          cb.onEvent?.(ev)
        },
        onClosed: (code, reason) => {
          if (outcome !== 'deepgram') return
          onLost(`Deepgram closed (${code})${reason ? ` ${reason}` : ''}`)
        },
        onError: (err, fatal) => {
          if (outcome === 'pending' && fatal) {
            outcome = 'failed'
            clearTimeout(timeout)
            try { handle?.stop() } catch { /* ignore */ }
            console.warn(`[deepgram ${source}] initial failure:`, err.message)
            resolve(null)
            return
          }
          if (outcome === 'deepgram') {
            cb.onError(err)
          }
        }
      },
      true, // useDeepgram = true
      fakeToken // Pass a fake token since Deepgram uses API key auth
    )
      .then((h) => {
        if (outcome === 'failed') {
          try { h.stop() } catch { /* ignore */ }
        } else {
          handle = h
        }
      })
      .catch((err) => {
        if (outcome !== 'pending') return
        outcome = 'failed'
        clearTimeout(timeout)
        console.warn(`[deepgram ${source}] start threw:`, err)
        resolve(null)
      })
  })
}

/**
 * Begin transcribing one audio source. Tries Deepgram first if configured,
 * falls back to Omi v4/listen.
 */
export async function startTranscription(
  source: ListenSource,
  cb: TranscriptionCallbacks
): Promise<TranscriptionHandle> {
  let active: OmiListenHandle | null = null

  // Check if Deepgram is available (IPC method exists)
  const useDeepgram = typeof window.omi?.deepgramListenStart === 'function'

  if (useDeepgram) {
    // Try Deepgram first (uses its own API key, no Firebase auth needed)
    console.log('[transcription] trying Deepgram...')
    const deepgramHandle = await startWithDeepgram(source, cb, (reason) => {
      cb.onError(new Error(`Deepgram transcription stopped: ${reason}`))
    })

    if (deepgramHandle) {
      console.log('[transcription] Deepgram connected successfully')
      active = deepgramHandle
    } else {
      // Deepgram failed, try Omi as fallback (requires Firebase auth)
      console.warn('[transcription] Deepgram failed, falling back to Omi')
      if (!auth.currentUser) {
        cb.onError(
          new Error('Transcription unavailable (Deepgram failed, not signed in for Omi fallback)')
        )
      } else {
        const omi = await startWithOmi(source, cb, (reason) => {
          cb.onError(new Error(`Omi transcription stopped: ${reason}`))
        })
        if (omi) {
          active = omi
        } else {
          cb.onError(new Error('Transcription unavailable (both Deepgram and Omi failed)'))
        }
      }
    }
  } else {
    // Use Omi only
    if (!auth.currentUser) {
      cb.onError(new Error('Omi transcription unavailable (not signed in)'))
    } else {
      const omi = await startWithOmi(source, cb, (reason) => {
        cb.onError(new Error(`Omi transcription stopped: ${reason}`))
      })
      if (omi) {
        active = omi
      } else {
        cb.onError(new Error('Omi transcription unavailable (could not connect)'))
      }
    }
  }

  return {
    stop: (): void => {
      try { active?.stop() } catch { /* ignore */ }
    }
  }
}
