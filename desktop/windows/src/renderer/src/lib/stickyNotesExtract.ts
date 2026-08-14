// Synthesize Windows Sticky Notes text into durable memories — the renderer half
// of parity item 3e, mirroring macOS AppleNotesReaderService. Routes through the
// backend connector-synthesis SSOT (POST /v1/connectors/synthesize) instead of
// building a notes prompt locally and calling Anthropic Haiku.
import { synthesizeConnectorItems } from './connectorSynthesis'

export type ExtractedMemories = { memories: string[]; profile: string }

/** Matches the per-item cap in connectorSynthesis.ts. */
const MAX_NOTE_LINE_CHARS = 1000

// Send the combined note text through backend synthesis and return the result.
// Throws on transport/auth failure so the caller can surface an error (no local
// fallback: notes are short and writing them verbatim pollutes memory).
export async function extractNoteMemories(
  notesText: string,
  existing: string[] = []
): Promise<ExtractedMemories> {
  const trimmed = notesText.trim()
  if (!trimmed) return { memories: [], profile: '' }

  // The synthesis transport caps each item at 1000 chars, so a single long note line
  // would lose its tail. Chunk long lines instead of dropping their content.
  const lines: string[] = []
  for (const raw of trimmed.slice(0, 40_000).split('\n')) {
    const line = raw.trim()
    if (!line) continue
    for (let i = 0; i < line.length; i += MAX_NOTE_LINE_CHARS) {
      lines.push(line.slice(i, i + MAX_NOTE_LINE_CHARS))
    }
  }

  const synthesis = await synthesizeConnectorItems('notes', lines, existing)
  return { memories: synthesis.memories, profile: synthesis.profile }
}
