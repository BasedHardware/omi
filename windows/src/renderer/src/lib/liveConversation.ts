import type { ListenEvent, TranscriptLine } from '../../../shared/types'

export type LiveStatus = 'idle' | 'connecting' | 'live' | 'error'

// Singleton store for the CURRENT in-progress conversation's live transcript.
// Both the background ContinuousRecordingHost (writer) and the LiveConversation
// view (reader) use it, so the live view shows whatever the always-on stream is
// capturing. Cleared when the backend signals a conversation boundary.
let segments: TranscriptLine[] = []
let status: LiveStatus = 'idle'
let errorMsg: string | null = null
// True right after a conversation was finalized/saved: the transcript stays on
// screen (flagged "saved") instead of blanking, and is cleared automatically when
// the next utterance arrives so the view never looks like a jarring new session.
let saved = false
// Title/emoji of the just-finalized conversation, shown in the live view header
// (empty title => "loading…") and filled in by the client-side titler.
let savedTitle = ''
let savedEmoji = ''
const subscribers = new Set<() => void>()

function notify(): void {
  subscribers.forEach((cb) => cb())
}

export const liveConversation = {
  getSegments(): TranscriptLine[] {
    return segments
  },
  getStatus(): LiveStatus {
    return status
  },
  getError(): string | null {
    return errorMsg
  },
  isSaved(): boolean {
    return saved
  },
  getSavedTopic(): { title: string; emoji: string } {
    return { title: savedTitle, emoji: savedEmoji }
  },
  // Mark the current transcript as saved/finalized but keep it on screen. The next
  // appendLine clears it (the next conversation has started). Title/emoji start
  // empty ("loading…") and are filled by setSavedTopic when the titler resolves.
  markSaved(): void {
    if (segments.length === 0) return
    saved = true
    savedTitle = ''
    savedEmoji = ''
    notify()
  },
  setSavedTopic(title: string, emoji: string): void {
    savedTitle = title
    savedEmoji = emoji
    notify()
  },
  appendLine(line: TranscriptLine): void {
    // The previous (saved) transcript stays visible until the next utterance —
    // clear it now that a new conversation is starting.
    if (saved) {
      segments = []
      saved = false
      savedTitle = ''
      savedEmoji = ''
    }
    // Upsert by backend segment id when present (segments are re-emitted as they
    // refine around pauses), else append.
    if (line.id) {
      const i = segments.findIndex((s) => s.id === line.id)
      if (i >= 0) {
        segments = segments.map((s, j) => (j === i ? line : s))
        notify()
        return
      }
    }
    segments = [...segments, line]
    notify()
  },
  setStatus(next: LiveStatus, error?: string): void {
    status = next
    // Keep the human-readable cause alongside the 'error' status; clear it on any
    // non-error transition so a recovered session doesn't show a stale message.
    errorMsg = next === 'error' ? (error ?? null) : null
    notify()
  },
  reset(): void {
    segments = []
    status = 'idle'
    errorMsg = null
    saved = false
    savedTitle = ''
    savedEmoji = ''
    notify()
  },
  subscribe(cb: () => void): () => void {
    subscribers.add(cb)
    return () => {
      subscribers.delete(cb)
    }
  }
}

// The backend emits `memory_creating` when it has decided the current
// conversation ended and is being turned into a memory. That's our cue to clear
// the live transcript and refresh the cloud conversation list. (Quota events are
// handled inside transcriptionClient, not here.)
export function isConversationBoundary(event: ListenEvent): boolean {
  return event.type === 'memory_creating'
}

// "Save now": a user-driven request to finalize the current conversation
// immediately (instead of waiting for the backend's silence boundary). Whoever
// owns the active mic session — the always-on host or the one-off live view —
// subscribes and responds by ending its session (which makes the backend store
// the conversation) and starting a fresh one.
const finalizeSubscribers = new Set<() => void>()

export function onFinalizeRequest(cb: () => void): () => void {
  finalizeSubscribers.add(cb)
  return () => {
    finalizeSubscribers.delete(cb)
  }
}

export function requestFinalize(): void {
  finalizeSubscribers.forEach((cb) => cb())
}
