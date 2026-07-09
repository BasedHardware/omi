import { auth } from './firebase'
import { startOmiListen, type OmiListenHandle } from './omiListenClient'
import { getPreferences } from './preferences'
import type {
  BackendSegment,
  ListenSource,
  SttMode,
  TranscriptLine,
  TranscriptionBackend
} from '../../../shared/types'

const CLOUD_CONNECT_TIMEOUT_MS = 3000
const LOCAL_CONNECT_TIMEOUT_MS = 5 * 60_000

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
  if (backend !== 'local-parakeet') return 'cloud'
  // Send the user's true preference to main: only an explicit Local Parakeet
  // selection may trigger a first-use runtime/model install. Any other
  // preference maps local attempts to 'auto', which main serves only from an
  // already-installed runtime (falling back to cloud otherwise).
  return (getPreferences().sttMode ?? 'auto') === 'local-parakeet' ? 'local-parakeet' : 'auto'
}

/**
 * True only when the local Parakeet runtime is already installed and healthy.
 * Deliberately ignores `runtime.canInstall`: a merely-installable runtime must
 * not pull automatic modes onto the local path, because that would download
 * native runtime artifacts and model files without an explicit user choice.
 */
async function localSttInstalled(): Promise<boolean> {
  try {
    const status = await window.omi.localSttStatus()
    return status.available
  } catch {
    return false
  }
}

async function initialBackendOrder(): Promise<TranscriptionBackend[]> {
  const preference = getPreferences().sttMode ?? 'auto'
  if (preference === 'cloud') {
    return (await localSttInstalled()) ? ['omi', 'local-parakeet'] : ['omi']
  }
  if (preference === 'local-parakeet') return ['local-parakeet', 'omi']
  return (await localSttInstalled()) ? ['local-parakeet', 'omi'] : ['omi']
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
  onLost: (reason: string, backend: TranscriptionBackend) => void
): Promise<OmiListenHandle | null> {
  if (!auth.currentUser) return null
  let outcome: 'pending' | 'connected' | 'failed' = 'pending'
  // Main can answer a local-parakeet 'auto' attempt with the cloud backend
  // (e.g. the installed runtime broke between checks). Track what actually
  // connected so quota/close handling matches the live backend.
  let effectiveBackend: TranscriptionBackend = backend
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
          effectiveBackend = actualBackend
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
          if (effectiveBackend !== 'omi' || !isQuotaExhaustedEvent(ev)) return
          // Free quota is used up — the cloud STT will never emit transcripts.
          if (outcome === 'pending') {
            outcome = 'failed'
            clearTimeout(timeout)
            void handle?.stop().catch(() => undefined)
            resolve(null)
          } else if (outcome === 'connected') {
            onLost('Omi free quota exhausted', effectiveBackend)
          }
        },
        onClosed: (code, reason) => {
          if (outcome !== 'connected') return
          const message =
            effectiveBackend === 'omi'
              ? isQuotaClose(code, reason)
                ? QUOTA_MESSAGE
                : `Omi /v4/listen closed (${code})${reason ? ` ${reason}` : ''}`
              : `Local Parakeet STT closed (${code})${reason ? ` ${reason}` : ''}`
          onLost(message, effectiveBackend)
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
            if (effectiveBackend === 'omi' && isTrialExpiredError(err)) {
              onLost(QUOTA_MESSAGE, effectiveBackend)
              return
            }
            onLost(err.message, effectiveBackend)
          }
        }
      },
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
 * Begin transcribing one audio source. Auto mode uses local Parakeet only when
 * the local runtime is already installed and healthy; otherwise it uses Omi
 * /v4/listen and never installs anything. Only the explicit 'local-parakeet'
 * preference may trigger the first-use runtime/model install. Local
 * model/runtime failure falls back to hosted cloud, and hosted startup/loss can
 * try local once when the runtime is already installed.
 */
export async function startTranscription(
  source: ListenSource,
  cb: TranscriptionCallbacks
): Promise<TranscriptionHandle> {
  let active: OmiListenHandle | null = null
  let stopped = false
  const tried = new Set<TranscriptionBackend>()

  const activate = async (backend: TranscriptionBackend): Promise<OmiListenHandle | null> => {
    if (stopped || tried.has(backend)) return null
    tried.add(backend)
    return startWithBackend(source, backend, cb, (reason, lostBackend) => {
      if (stopped) return
      const fallback: TranscriptionBackend = lostBackend === 'omi' ? 'local-parakeet' : 'omi'
      void (async () => {
        if (fallback === 'local-parakeet' && !(await localSttInstalled())) {
          if (stopped) return
          cb.onError(new Error(`Transcription stopped: ${reason}`))
          return
        }
        const next = await activate(fallback)
        if (stopped) {
          void next?.stop().catch(() => undefined)
          return
        }
        if (next) {
          active = next
          return
        }
        cb.onError(new Error(`Transcription stopped: ${reason}`))
      })()
    })
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
