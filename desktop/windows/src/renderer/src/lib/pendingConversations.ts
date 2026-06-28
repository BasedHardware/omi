import { addPendingConversation, setPendingTopic } from './pageCache'
import { generateConversationTopic } from './conversationTopic'
import { liveConversation } from './liveConversation'
import type { TranscriptLine } from '../../../shared/types'

// Turn finalized live segments into a transcript string for titling/preview.
function segmentsToTranscript(segments: TranscriptLine[]): string {
  return segments
    .map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text))
    .filter(Boolean)
    .join('\n')
    .trim()
}

/**
 * On finalize, show the conversation in the list immediately as a "loading"
 * placeholder, then fill its title + emoji client-side (fast) so it doesn't wait
 * on the slow backend. The placeholder is dropped by reconcilePending once the
 * backend's real cloud conversation for the same window arrives.
 */
export function createPendingConversation(segments: TranscriptLine[]): void {
  const transcript = segmentsToTranscript(segments)
  if (!transcript) return
  const id = addPendingConversation(transcript)
  void generateConversationTopic(transcript).then((t) => {
    if (!t) return
    setPendingTopic(id, t.title, t.emoji) // the Conversations list
    liveConversation.setSavedTopic(t.title, t.emoji) // the live view header
  })
}
