// Synthesize Windows Sticky Notes text into durable memories — the renderer half
// of parity item 3e, mirroring macOS AppleNotesReaderService. Routes through the
// backend connector-synthesis SSOT (POST /v1/connectors/synthesize) instead of
// building a notes prompt locally and calling Anthropic Haiku.
import { synthesizeConnectorItems } from './connectorSynthesis'

export type ExtractedMemories = { memories: string[]; profile: string }

// Send the combined note text through backend synthesis and return the result.
// Throws on transport/auth failure so the caller can surface an error (no local
// fallback: notes are short and writing them verbatim pollutes memory).
export async function extractNoteMemories(
  notesText: string,
  existing: string[] = []
): Promise<ExtractedMemories> {
  const trimmed = notesText.trim()
  if (!trimmed) return { memories: [], profile: '' }

  const lines = trimmed
    .slice(0, 40_000)
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.length > 0)

  const synthesis = await synthesizeConnectorItems('notes', lines, existing)
  return { memories: synthesis.memories, profile: synthesis.profile }
}
