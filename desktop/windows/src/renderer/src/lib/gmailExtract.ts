// Synthesize Gmail metadata (Subject/From/snippet — never bodies) into durable,
// atomic memories through the backend connector-synthesis SSOT. Mirrors
// stickyNotesExtract.ts; only the row formatting is Gmail-specific.
import { synthesizeConnectorItems } from './connectorSynthesis'
import type { GmailItem } from '../../../shared/types'

export function formatGmailItems(items: GmailItem[]): string[] {
  return items
    .slice(0, 50)
    .map((it) => `From: ${it.from} | Subject: ${it.subject} | ${it.snippet}`.slice(0, 500))
}

export async function extractGmailMemories(
  items: GmailItem[],
  existing: string[] = []
): Promise<string[]> {
  if (items.length === 0) return []
  const synthesis = await synthesizeConnectorItems('gmail', formatGmailItems(items), existing)
  return synthesis.memories
}
