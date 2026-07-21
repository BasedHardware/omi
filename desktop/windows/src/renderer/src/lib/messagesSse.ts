// Reconstruct the assistant reply from Omi's /v2/messages SSE response when it's
// consumed as one buffered string (not streamed). The per-line rules live in the
// shared parser (src/shared/omiSse.ts) so this can't drift from useChat's
// streaming parse or the main-process reply engine.
import { parseOmiSseLine } from '../../../shared/omiSse'

export function parseMessagesSse(raw: string): string {
  const out: string[] = []
  for (const line of raw.split('\n')) {
    const content = parseOmiSseLine(line)
    if (content !== null) out.push(content)
  }
  return out.join('')
}
