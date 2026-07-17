import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import { isConversationBoundary, onFinalizeRequest } from '../lib/liveConversation'
import { transcriptWordCount } from '../lib/retentionRules'
import { isInjectedLineId } from '../lib/voice/injectedTranscript'
import { syncLocalConversation } from '../lib/sync/conversationSync'
import { captureLiveStore } from './liveStore'
import {
  MAX_RECONNECT_ATTEMPTS,
  reconnectDelayMs,
  isRetryableDropError,
  toSyncSegments,
  segmentsToTranscript,
  createSegmentRetainer
} from './liveRescue'
import type { LocalConversation } from '../../../shared/types'

// After this much silence (no new finalized speech) the current conversation is
// finalized: the session ends so the backend stores it, then a fresh one starts.
const SILENCE_MS = 30000
// Below this word count a transcript is a trivial blip not worth its own
// conversation — used both by finalize and by the reconnect-exhausted rescue.
const MIN_WORDS = 5

export type LiveMicController = {
  /** Stop the session and tear everything down (call from effect cleanup). */
  stop: () => void
}

// How many always-on mic controllers are live right now. The continuous mic
// session already streams the mic to the backend's /v4/listen conversation, so a
// concurrently-detected meeting must NOT open a second mic /v4/listen for the same
// audio (C6). Both hosts run in the capture window, so this module-level count is
// the shared "is the mic already owned?" signal. Kept as a count (not a boolean)
// so a StrictMode double-mount never wedges it false.
let liveMicActiveCount = 0

/** True when an always-on continuous mic session is running. Read by the meeting
 *  session to defer to it instead of opening a duplicate mic /v4/listen. */
export function isLiveMicSessionActive(): boolean {
  return liveMicActiveCount > 0
}

/**
 * The single owner of an always-on mic → /v4/listen session that drives the
 * shared `liveConversation` store. Runs INSIDE the capture window (mounted by
 * ContinuousSessionHost) so capture is independent of any UI window. It handles:
 * connect, feeding segments into the live store, the 30s-silence and "Save now"
 * finalize (end → store → restart), the backend's own boundary, resilient
 * reconnect that RESUMES the same conversation across a socket drop, a
 * from-segments rescue when reconnect is exhausted, and a StrictMode-safe deferred
 * connect.
 *
 * Resilience (fixes: any close was terminal → a network blip lost the recording):
 *  - Each conversation carries a client-generated `clientConversationId`. A dropped
 *    socket reconnects with capped backoff (up to MAX_RECONNECT_ATTEMPTS) re-sending
 *    that SAME id, so the backend resumes the in-progress conversation instead of
 *    stranding it (transcribe.py keys the conversation on client_conversation_id).
 *  - Raw segments are retained for the current conversation. If every reconnect
 *    fails (an extended outage), the retained segments are pushed through the sync
 *    outbox as a from-segments upload so the recording survives — as 'unconfirmed'
 *    so the outbox dedupes against the cloud first and never double-creates.
 *
 * Every store mutation goes through `captureLiveStore`, which mirrors it to UI
 * windows as a LiveStoreOp. On finalize it broadcasts a `saved` op carrying the
 * segments; the UI window (LiveMirrorHost) turns that into an optimistically-
 * titled pending conversation and refreshes the cloud list — those UI side
 * effects deliberately do NOT run here (this window has no UI).
 */
export function startLiveMicSession(): LiveMicController {
  let cancelled = false
  liveMicActiveCount++ // mark the mic as owned (see isLiveMicSessionActive / C6)
  let handle: TranscriptionHandle | null = null
  let hasSpeech = false
  let silenceTimer: ReturnType<typeof setTimeout> | null = null
  const timers: ReturnType<typeof setTimeout>[] = []

  // Per-conversation state, reset by startConversation() at each boundary.
  let clientConversationId = crypto.randomUUID()
  let conversationStartedAt = Date.now()
  let reconnectAttempt = 0
  let retainer = createSegmentRetainer()

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
  // rules use) — trivial blips below this aren't worth finalizing. Injected
  // assistant lines (Omi's own words, Phase 6) are EXCLUDED so they can't push
  // an otherwise-trivial human blip over the finalize threshold.
  const liveWordCount = (): number =>
    transcriptWordCount(
      captureLiveStore
        .getSegments()
        .filter((s) => !isInjectedLineId(s.id))
        .map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text))
        .join('\n')
    )

  // Save the just-spoken transcript as its own conversation: broadcast the saved
  // segments (the UI window titles + lists them) and keep them on the live screen
  // flagged "saved", then start a fresh session so capture continues.
  const saveCurrent = (): void => {
    captureLiveStore.saved(captureLiveStore.getSegments())
  }

  // Reconnect exhausted: the backend was unreachable, so its own conversation was
  // never finalized. Persist what we captured and push it through the sync outbox
  // as a from-segments upload so the recording isn't lost. Inserted as
  // 'unconfirmed' so the outbox runs its dedupe-against-cloud BEFORE posting — if
  // the backend DID manage to finalize a conversation from the pre-drop audio we
  // adopt it instead of creating a duplicate.
  const rescue = (): void => {
    const segs = retainer.list()
    const transcript = segmentsToTranscript(segs)
    if (transcriptWordCount(transcript) < MIN_WORDS) return
    const row: LocalConversation = {
      id: `local-${crypto.randomUUID()}`,
      startedAt: conversationStartedAt,
      endedAt: Date.now(),
      transcript,
      createdAt: Date.now(),
      syncState: 'unconfirmed',
      segments: toSyncSegments(segs)
    }
    void window.omi
      .insertLocalConversation(row)
      .then(() => {
        window.omi.notifyConversationsChanged?.()
        return syncLocalConversation(row)
      })
      .catch((e) => console.warn('[live-mic] rescue upload failed:', (e as Error).message))
  }

  // Finalize on the silence timeout or "Save now": end the session (the backend
  // stores it), then restart. No-op if nothing was said since the last finalize.
  const finalize = (): void => {
    if (cancelled || !hasSpeech) return
    // Don't make a conversation out of a trivial blip (< 5 words) — keep
    // listening so it merges into the next real one.
    if (liveWordCount() < MIN_WORDS) {
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
    startConversation() // fresh conversation: new resumable id, cleared retainer
  }

  // Open (or reconnect) the socket for the CURRENT conversation, re-sending the
  // same clientConversationId so a reconnect resumes it.
  const connect = (): void => {
    captureLiveStore.setStatus('connecting')
    void startTranscription(
      'mic',
      {
        onLine: (line) => {
          if (cancelled) return
          reconnectAttempt = 0 // a delivered segment proves the socket is healthy
          captureLiveStore.setStatus('live')
          captureLiveStore.appendLine(line)
          hasSpeech = true
          armSilence() // reset the silence countdown on each new utterance
        },
        onInterim: () => {},
        onBackend: () => {
          if (cancelled) return
          reconnectAttempt = 0
          captureLiveStore.setStatus('live')
        },
        onSegments: (segs) => {
          if (!cancelled) retainer.add(segs) // retained for the exhausted-reconnect rescue
        },
        onEvent: (ev) => {
          if (cancelled) return
          if (isConversationBoundary(ev)) {
            // Backend finalized on its own (beat our silence timer). Skip trivial
            // blips; otherwise keep the transcript shown as saved, and reset the
            // rescue window so it scopes to the next conversation.
            clearSilence()
            hasSpeech = false
            if (liveWordCount() >= MIN_WORDS) saveCurrent()
            retainer = createSegmentRetainer()
            conversationStartedAt = Date.now()
          }
        },
        onError: (e) => {
          if (cancelled) return
          try {
            handle?.stop()
          } catch {
            /* ignore */
          }
          handle = null
          if (!isRetryableDropError((e as Error).message)) {
            // Quota/entitlement/sign-in error — reconnecting can't help. Surface it
            // now (no rescue: a quota-blocked account can't create conversations).
            // On a quota exhaustion this mirrored 'error' status drives the main
            // window's LiveMirrorHost → maybeTriggerTranscriptionQuotaPopup, which
            // raises the "Upgrade" modal. Do NOT call showUsageLimit here: this
            // hidden capture window is a separate renderer, so its in-memory popup
            // signal never reaches the popup host.
            captureLiveStore.setStatus('error', (e as Error).message)
            return
          }
          if (reconnectAttempt < MAX_RECONNECT_ATTEMPTS) {
            // Transient drop (or connect failure) — reconnect and RESUME the same
            // conversation. The retainer + live store are preserved across this.
            reconnectAttempt++
            captureLiveStore.setStatus('connecting')
            timers.push(
              setTimeout(() => {
                if (!cancelled) connect()
              }, reconnectDelayMs(reconnectAttempt))
            )
          } else {
            // Exhausted — rescue the recording via from-segments, then surface the error.
            rescue()
            captureLiveStore.setStatus('error', (e as Error).message)
          }
        }
      },
      'conversation',
      clientConversationId
    ).then((h) => {
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

  // Begin a fresh conversation: new resumable id, cleared retainer, reset backoff.
  function startConversation(): void {
    clientConversationId = crypto.randomUUID()
    conversationStartedAt = Date.now()
    reconnectAttempt = 0
    retainer = createSegmentRetainer()
    connect()
  }

  captureLiveStore.reset()
  // Defer the initial connect a macrotask so React dev StrictMode's
  // mount→unmount→remount doesn't open two competing /v4/listen sessions (the
  // second "could not connect"); this controller's stop() clears it first.
  timers.push(setTimeout(startConversation, 0))
  const unsubFinalize = onFinalizeRequest(finalize)

  return {
    stop: (): void => {
      if (cancelled) return // idempotent — decrement the active count exactly once
      cancelled = true
      liveMicActiveCount = Math.max(0, liveMicActiveCount - 1)
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
