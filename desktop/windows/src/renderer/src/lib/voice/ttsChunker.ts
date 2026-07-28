// Split a complete reply into TTS-sized chunks, matching the macOS
// FloatingBarVoicePlaybackService boundaries (FloatingBarVoicePlaybackService.swift
// `nextChunkBoundary` + the firstChunk/followupChunk length constants):
//
//  - a SMALL first chunk (40–200 chars) so playback starts fast, then
//  - larger FOLLOW chunks (320–800) so a long reply is stitched from fewer
//    generated clips (each clip carries leading/trailing silence, so fewer
//    chunks = far less perceived pausing).
//
// Within each chunk's window the cut is taken at the highest-priority boundary
// available: sentence punctuation (. ! ? \n) > clause punctuation (, ; : \n) >
// whitespace > a hard cut at the emergency length. Windows synthesizes the whole
// reply text at once (not streamed like macOS), so this is a one-shot splitter
// rather than an incremental drain, but the per-chunk boundary logic is identical.

export const FIRST_CHUNK = { min: 40, preferred: 120, emergency: 200 } as const
export const FOLLOW_CHUNK = { min: 320, preferred: 520, emergency: 800 } as const

const SENTENCE = '.!?\n'
const CLAUSE = ',;:\n'

function lastIndexOfAny(text: string, chars: string): number {
  for (let i = text.length - 1; i >= 0; i--) {
    if (chars.includes(text[i])) return i
  }
  return -1
}

function lastWhitespaceIndex(text: string): number {
  for (let i = text.length - 1; i >= 0; i--) {
    if (/\s/.test(text[i])) return i
  }
  return -1
}

/**
 * The exclusive end index of the next chunk within `text`, or `null` when there
 * is not yet enough text for a full chunk (the caller flushes the remainder as
 * the final chunk). Port of macOS `nextChunkBoundary(in:isFinal:isFirstChunk:)`
 * with `isFinal == false`.
 */
export function nextChunkBoundary(text: string, isFirstChunk: boolean): number | null {
  const t = isFirstChunk ? FIRST_CHUNK : FOLLOW_CHUNK
  if (text.length < t.min) return null

  const preferredSlice = text.slice(0, Math.min(text.length, t.preferred))
  let idx = lastIndexOfAny(preferredSlice, SENTENCE)
  if (idx >= 0) return idx + 1

  if (text.length < t.preferred) return null

  const emergencySlice = text.slice(0, Math.min(text.length, t.emergency))
  idx = lastIndexOfAny(emergencySlice, SENTENCE)
  if (idx >= 0) return idx + 1

  if (text.length < t.emergency) return null

  idx = lastIndexOfAny(emergencySlice, CLAUSE)
  if (idx >= 0) return idx + 1

  idx = lastWhitespaceIndex(emergencySlice)
  if (idx >= 0) return idx // whitespace boundary — the space itself is dropped

  return emergencySlice.length // hard cut at the emergency length
}

/** Split the full reply into ordered, non-empty, trimmed chunks. A reply short
 *  enough to need no mid-cut returns a single chunk (preserving the original
 *  synth-whole-then-play behavior). */
export function chunkTts(text: string): string[] {
  const chunks: string[] = []
  let buffer = text.trim()
  while (buffer.length > 0) {
    const isFirst = chunks.length === 0
    const boundary = nextChunkBoundary(buffer, isFirst)
    if (boundary === null) {
      // Not enough remaining for another full chunk — flush it as the last one.
      chunks.push(buffer)
      break
    }
    const chunk = buffer.slice(0, boundary).trim()
    buffer = buffer.slice(boundary).trim()
    if (chunk) chunks.push(chunk)
  }
  return chunks
}
