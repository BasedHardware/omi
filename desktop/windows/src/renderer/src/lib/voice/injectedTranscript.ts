// Injected-transcript formatting (Phase 6). While the echo gate pauses the
// always-on transcription feed, Omi's spoken words still belong in the record —
// injected from SOURCE TEXT (the provider's own output transcript / the TTS
// input string), never re-transcribed from the speaker. Pure so formatting is
// unit-testable; ContinuousSessionHost applies the result to the live store.

import type { TranscriptLine } from '../../../../shared/types'

export const ASSISTANT_SPEAKER = 'Omi'

/** Line-id prefix for every injected assistant line (realtime AND TTS — TTS
 *  utterance ids arrive as 'tts-N' and become 'omi-voice-tts-N'). */
export const INJECTED_LINE_ID_PREFIX = 'omi-voice-'

/** True for transcript lines that were INJECTED from assistant source text
 *  (vs transcribed speech). Consumers whose heuristics reason about what the
 *  USER said (e.g. the finalize word-count) must exclude these. */
export function isInjectedLineId(id: string | undefined): boolean {
  return typeof id === 'string' && id.startsWith(INJECTED_LINE_ID_PREFIX)
}

/** Live-store statuses into which injecting a line is meaningful (a session is
 *  running, so the line lands in a real conversation record). When idle or
 *  errored there is no record to join — injecting would strand the line in a
 *  dead store and leak it into the NEXT session's view. */
export function shouldInjectIntoLive(status: 'idle' | 'connecting' | 'live' | 'error'): boolean {
  return status === 'connecting' || status === 'live'
}

/**
 * Format one spoken assistant utterance as a transcript line. Collapses
 * whitespace (provider transcripts arrive with streaming artifacts) and
 * returns null for empty/whitespace text so callers never append blank lines.
 * `utteranceId` must be stable per utterance (the capture window may receive
 * the same utterance twice across a window reload; stable ids let the store
 * upsert instead of duplicating).
 */
export function formatAssistantLine(text: string, utteranceId: string): TranscriptLine | null {
  const cleaned = text.replace(/\s+/g, ' ').trim()
  if (!cleaned) return null
  return {
    id: `${INJECTED_LINE_ID_PREFIX}${utteranceId}`,
    speaker: ASSISTANT_SPEAKER,
    text: cleaned
  }
}
