import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import { isConversationBoundary, onFinalizeRequest } from '../lib/liveConversation'
import { transcriptWordCount } from '../lib/retentionRules'
import { captureLiveStore } from './liveStore'

// After this much silence (no new finalized speech) the current conversation is
// finalized: the session ends so the backend stores it, then a fresh one starts.
const SILENCE_MS = 30000
// Connect retries before surfacing the error (rides through the dev StrictMode
// double-mount mic race and slow first connects).
const MAX_ATTEMPTS = 3

export type LiveMicController = {
  /** Stop the session and tear everything down (call from effect cleanup). */
  stop: () => void
}

/**
 * The single owner of an always-on mic → /v4/listen session that drives the
 * shared `liveConversation` store. Runs INSIDE the capture window (mounted by
 * ContinuousSessionHost) so capture is independent of any UI window. It handles:
 * connect-with-retry, feeding segments into the live store, the 30s-silence and
 * "Save now" finalize (end → store → restart), the backend's own boundary, and a
 * StrictMode-safe deferred connect.
 *
 * Every store mutation goes through `captureLiveStore`, which mirrors it to UI
 * windows as a LiveStoreOp. On finalize it broadcasts a `saved` op carrying the
 * segments; the UI window (LiveMirrorHost) turns that into an optimistically-
 * titled pending conversation and refreshes the cloud list — those UI side
 * effects deliberately do NOT run here (this window has no UI).
 */
export function startLiveMicSession(): LiveMicController {
  let cancelled = false
  let handle: TranscriptionHandle | null = null
  let attempt = 0
  let hasSpeech = false
  let silenceTimer: ReturnType<typeof setTimeout> | null = null
  const timers: ReturnType<typeof setTimeout>[] = []

  const clearSilence = (): void => {
    if (silenceTimer) clearTimeout(silenceTimer)
    silenceTimer = null
  }

  const armSilence = (): void => {
    clearSilence()
    silenceTimer = setTimeout(() => {
      if (!cancelled && hasSpeech) finalize()
    }, SILENCE_MS)
  }

  // Words in the current live transcript (using the same counter the retention
  // rules use) — trivial blips below this aren't worth finalizing.
  const liveWordCount = (): number =>
    transcriptWordCount(
      captureLiveStore
        .getSegments()
        .map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text))
        .join('\n')
    )

  // Save the just-spoken transcript as its own conversation: broadcast the saved
  // segments (the UI window titles + lists them) and keep them on the live screen
  // flagged "saved", then start a fresh session so capture continues.
  const saveCurrent = (): void => {
    captureLiveStore.saved(captureLiveStore.getSegments())
  }

  // Finalize on the silence timeout or "Save now": end the session (the backend
  // stores it), then restart. No-op if nothing was said since the last finalize.
  const finalize = (): void => {
    if (cancelled || !hasSpeech) return
    // Don't make a conversation out of a trivial blip (< 5 words) — keep
    // listening so it merges into the next real one.
    if (liveWordCount() < 5) {
      armSilence()
      return
    }
    hasSpeech = false
    clearSilence()
    try {
      handle?.stop()
    } catch {
      /* ignore */
    }
    handle = null
    saveCurrent()
    attempt = 0
    startSession()
  }

  const startSession = (): void => {
    captureLiveStore.setStatus('connecting')
    void startTranscription('mic', {
      onLine: (line) => {
        if (cancelled) return
        captureLiveStore.setStatus('live')
        captureLiveStore.appendLine(line)
        hasSpeech = true
        armSilence() // reset the silence countdown on each new utterance
      },
      onInterim: () => {},
      onBackend: () => {
        if (!cancelled) captureLiveStore.setStatus('live')
      },
      onEvent: (ev) => {
        if (cancelled) return
        if (isConversationBoundary(ev)) {
          // Backend finalized on its own (beat our silence timer). Skip trivial
          // blips; otherwise keep the transcript shown as saved.
          clearSilence()
          hasSpeech = false
          if (liveWordCount() >= 5) saveCurrent()
        }
      },
      onError: (e) => {
        if (cancelled) return
        if (attempt < MAX_ATTEMPTS) {
          attempt++
          captureLiveStore.setStatus('connecting')
          timers.push(setTimeout(startSession, 800 * attempt))
        } else {
          captureLiveStore.setStatus('error', (e as Error).message)
        }
      }
    }).then((h) => {
      if (cancelled) {
        try {
          h.stop()
        } catch {
          /* ignore */
        }
        return
      }
      handle = h
    })
  }

  captureLiveStore.reset()
  // Defer the initial connect a macrotask so React dev StrictMode's
  // mount→unmount→remount doesn't open two competing /v4/listen sessions (the
  // second "could not connect"); this controller's stop() clears it first.
  timers.push(setTimeout(startSession, 0))
  const unsubFinalize = onFinalizeRequest(finalize)

  return {
    stop: (): void => {
      cancelled = true
      clearSilence()
      timers.forEach(clearTimeout)
      unsubFinalize()
      try {
        handle?.stop()
      } catch {
        /* ignore */
      }
      handle = null
      captureLiveStore.reset()
    }
  }
}
