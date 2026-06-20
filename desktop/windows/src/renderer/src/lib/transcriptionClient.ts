import { auth } from './firebase'
import { startOmiListen, type OmiListenHandle } from './omiListenClient'
import { getPreferences } from './preferences'
import type { RecordingDiagnosticsScope } from './continuousRecordingStatus'
import type {
  BackendSegment,
  ListenSource,
  SttMode,
  TranscriptLine,
  TranscriptionBackend
} from '../../../shared/types'

const CLOUD_CONNECT_TIMEOUT_MS = 3000
const LOCAL_CONNECT_TIMEOUT_MS = 10000

export type TranscriptionCallbacks = {
  /** Fires every time a new finalized line is ready. */
  onLine: (line: TranscriptLine) => void
  /** Reserved for in-progress interim text. The current backends emit finalized segments only. */
  onInterim: (text: string) => void
  /** Fires once when the winning backend connects. */
  onBackend: (backend: TranscriptionBackend) => void
  /** Fires when transcription can't start or can't continue. */
  onError: (err: Error) => void
  /** Fires for every non-segment backend event. Optional; quota events are still handled internally. */
  onEvent?: (event: { type: string; raw: Record<string, unknown> }) => void
}

export type TranscriptionHandle = {
  stop: () => Promise<void>
}

function segmentToLine(seg: BackendSegment): TranscriptLine {
  const speaker = seg.is_user
    ? 'You'
    : seg.speaker
      ? seg.speaker
      : typeof seg.speaker_id === 'number'
        ? `Speaker ${seg.speaker_id}`
        : undefined
  return {
    id: seg.id,
    speaker,
    text: seg.text,
    speakerId: seg.speaker_id,
    isUser: seg.is_user,
    personId: seg.person_id,
    start: seg.start,
    end: seg.end
  }
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

function modeForBackend(backend: TranscriptionBackend): SttMode {
  return backend === 'local-parakeet' ? 'local-parakeet' : 'cloud'
}

async function localSttAvailable(): Promise<boolean> {
  try {
    return (await window.omi.localSttStatus()).available
  } catch {
    return false
  }
}

async function initialBackendOrder(): Promise<TranscriptionBackend[]> {
  const preference = getPreferences().sttMode ?? 'auto'
  if (preference === 'cloud') {
    return (await localSttAvailable()) ? ['omi', 'local-parakeet'] : ['omi']
  }
  if (preference === 'local-parakeet') return ['local-parakeet', 'omi']
  return (await localSttAvailable()) ? ['local-parakeet', 'omi'] : ['omi']
}

/**
 * Start one selected backend for one source. Resolves the handle once the
 * backend connects, or null on an initial failure. `onLost` fires when a
 * connected session can no longer continue so the owner can try the other
 * backend or surface an error.
 */
async function startWithBackend(
  source: ListenSource,
  backend: TranscriptionBackend,
  cb: TranscriptionCallbacks,
  onLost: (reason: string, backend: TranscriptionBackend) => void,
  diagnosticsScope: RecordingDiagnosticsScope
): Promise<OmiListenHandle | null> {
  if (!auth.currentUser) return null
  let outcome: 'pending' | 'connected' | 'failed' = 'pending'
  return new Promise<OmiListenHandle | null>((resolve) => {
    let handle: OmiListenHandle | null = null
    const timeout = setTimeout(
      () => {
        if (outcome !== 'pending') return
        outcome = 'failed'
        void handle?.stop().catch(() => undefined)
        resolve(null)
      },
      backend === 'local-parakeet' ? LOCAL_CONNECT_TIMEOUT_MS : CLOUD_CONNECT_TIMEOUT_MS
    )

    startOmiListen(
      source,
      {
        onConnected: (actualBackend) => {
          if (outcome !== 'pending') return
          outcome = 'connected'
          clearTimeout(timeout)
          cb.onBackend(actualBackend)
          resolve(handle)
        },
        onSegments: (segs) => {
          if (outcome !== 'connected') return
          for (const s of segs) cb.onLine(segmentToLine(s))
        },
        onEvent: (ev) => {
          cb.onEvent?.(ev)
          if (backend !== 'omi' || !isQuotaExhaustedEvent(ev)) return
          // Free quota is used up — the cloud STT will never emit transcripts.
          if (outcome === 'pending') {
            outcome = 'failed'
            clearTimeout(timeout)
            void handle?.stop().catch(() => undefined)
            resolve(null)
          } else if (outcome === 'connected') {
            onLost('Omi free quota exhausted', backend)
          }
        },
        onClosed: (code, reason) => {
          if (outcome !== 'connected') return
          const message =
            backend === 'omi'
              ? isQuotaClose(code, reason)
                ? QUOTA_MESSAGE
                : `Omi /v4/listen closed (${code})${reason ? ` ${reason}` : ''}`
              : `Local Parakeet STT closed (${code})${reason ? ` ${reason}` : ''}`
          onLost(message, backend)
        },
        onError: (err, fatal) => {
          if (outcome === 'pending' && fatal) {
            outcome = 'failed'
            clearTimeout(timeout)
            void handle?.stop().catch(() => undefined)
            console.warn(`[transcription ${backend} ${source}] initial failure:`, err.message)
            resolve(null)
            return
          }
          if (outcome === 'connected') {
            if (backend === 'omi' && isTrialExpiredError(err)) {
              onLost(QUOTA_MESSAGE, backend)
              return
            }
            onLost(err.message, backend)
          }
        }
      },
      diagnosticsScope,
      modeForBackend(backend)
    )
      .then((h) => {
        // startOmiListen resolves once capture + IPC are set up; the backend
        // handshake still decides the winner via onConnected/timeout.
        if (outcome === 'failed') {
          void h.stop().catch(() => undefined)
        } else {
          handle = h
        }
      })
      .catch((err) => {
        if (outcome !== 'pending') return
        outcome = 'failed'
        clearTimeout(timeout)
        console.warn(`[transcription ${backend} ${source}] start threw:`, err)
        resolve(null)
      })
  })
}

/**
 * Begin transcribing one audio source. Auto mode uses local Parakeet only when a
 * healthy supported local runtime is present; otherwise it uses Omi /v4/listen.
 * Local model/runtime failure falls back to hosted cloud, and hosted startup/loss
 * can try local once when the runtime is available.
 */
export async function startTranscription(
  source: ListenSource,
  cb: TranscriptionCallbacks,
  diagnosticsScope: RecordingDiagnosticsScope = 'recorder'
): Promise<TranscriptionHandle> {
  let active: OmiListenHandle | null = null
  let stopped = false
  const tried = new Set<TranscriptionBackend>()

  const activate = async (backend: TranscriptionBackend): Promise<OmiListenHandle | null> => {
    if (stopped || tried.has(backend)) return null
    tried.add(backend)
    return startWithBackend(
      source,
      backend,
      cb,
      (reason, lostBackend) => {
        if (stopped) return
        const fallback: TranscriptionBackend = lostBackend === 'omi' ? 'local-parakeet' : 'omi'
        void (async () => {
          if (fallback === 'local-parakeet' && !(await localSttAvailable())) {
            cb.onError(new Error(`Transcription stopped: ${reason}`))
            return
          }
          const next = await activate(fallback)
          if (next) {
            active = next
            return
          }
          cb.onError(new Error(`Transcription stopped: ${reason}`))
        })()
      },
      diagnosticsScope
    )
  }

  for (const backend of await initialBackendOrder()) {
    active = await activate(backend)
    if (active) break
  }

  if (!active) {
    cb.onError(
      new Error(
        auth.currentUser
          ? 'Omi transcription unavailable (could not connect)'
          : 'Omi transcription unavailable (not signed in)'
      )
    )
  }

  return {
    stop: async (): Promise<void> => {
      stopped = true
      await active?.stop()
    }
  }
}
