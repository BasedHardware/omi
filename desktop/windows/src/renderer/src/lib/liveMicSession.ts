import { startTranscription, type TranscriptionHandle } from './transcriptionClient'
import { liveConversation, isConversationBoundary, onFinalizeRequest } from './liveConversation'
import { refreshCloudConversations } from './pageCache'
import { createPendingConversation } from './pendingConversations'
import { transcriptWordCount } from './retentionRules'
import { buildLocalGraph } from './kgSynthesis'

// Force a local-KG rebuild so conversation-derived memories reach the brain map,
// throttled to once per 30 min (the rebuild is two LLM calls). Delayed so the
// backend has extracted memories from the just-saved conversation first.
let lastKgRebuildAt = 0
function requestKgRebuild(): void {
  const now = Date.now()
  if (now - lastKgRebuildAt < 30 * 60 * 1000) return
  lastKgRebuildAt = now
  setTimeout(() => void buildLocalGraph(), 120000)
}

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
 * shared `liveConversation` store. Used by BOTH the background
 * ContinuousRecordingHost (when continuous mode is on) and the one-off
 * LiveConversation view (when it's off) — only one runs at a time. It handles:
 * connect-with-retry, feeding segments into the live store, the 30s-silence and
 * "Save now" finalize (end → store → show optimistic titled row → restart), the
 * backend's own boundary, and a StrictMode-safe deferred connect.
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

  // Re-fetch /v1/conversations now and a few times after, so a just-finalized
  // conversation appears (and its title/emoji fill in) without a manual refresh.
  const pollForNewConversation = (): void => {
    refreshCloudConversations()
    for (const delay of [4000, 12000, 30000]) {
      timers.push(setTimeout(() => refreshCloudConversations(), delay))
    }
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
      liveConversation
        .getSegments()
        .map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text))
        .join('\n')
    )

  // Save the just-spoken transcript as its own conversation: show it in the list
  // instantly (titled client-side), keep it on the live screen flagged "saved",
  // and start a fresh session so capture continues.
  const saveCurrent = (): void => {
    createPendingConversation(liveConversation.getSegments())
    liveConversation.markSaved()
    pollForNewConversation()
    // New conversation-derived memories should reach the brain map without waiting
    // for the next launch; force a throttled KG rebuild (helper above).
    requestKgRebuild()
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
    try { handle?.stop() } catch { /* ignore */ }
    handle = null
    saveCurrent()
    attempt = 0
    startSession()
  }

  const startSession = (): void => {
    liveConversation.setStatus('connecting')
    void startTranscription('mic', {
      onLine: (line) => {
        if (cancelled) return
        liveConversation.setStatus('live')
        liveConversation.appendLine(line)
        hasSpeech = true
        armSilence() // reset the silence countdown on each new utterance
      },
      onInterim: () => {},
      onBackend: () => {
        if (!cancelled) liveConversation.setStatus('live')
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
          liveConversation.setStatus('connecting')
          timers.push(setTimeout(startSession, 800 * attempt))
        } else {
          liveConversation.setStatus('error', (e as Error).message)
        }
      }
    }).then((h) => {
      if (cancelled) {
        try { h.stop() } catch { /* ignore */ }
        return
      }
      handle = h
    })
  }

  liveConversation.reset()
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
      try { handle?.stop() } catch { /* ignore */ }
      handle = null
      liveConversation.reset()
      refreshCloudConversations()
    }
  }
}
