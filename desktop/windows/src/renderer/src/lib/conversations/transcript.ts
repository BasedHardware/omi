// Shared transcript helpers for conversations: format the plain-text transcript
// from segments (the "Copy transcript" text) and load a row's transcript on
// demand. A list row carries no transcript (unlike the open detail view), so the
// row context menu has to fetch/read it when the user copies.

import { omiApi } from '../apiClient'
import type { Conversation, TranscriptSegment } from '../omiApi.generated'
import type { ConversationRow } from '../pageCache'

/** One line per segment, `Speaker: text` — the exact format the detail view's
 *  "Copy transcript" produces. Shared so the row context menu can't drift from
 *  it. */
export function buildTranscriptText(segments: TranscriptSegment[]): string {
  return segments
    .map((s) => `${s.is_user ? 'You' : (s.speaker ?? 'Speaker')}: ${s.text}`)
    .join('\n')
}

/** Load a conversation's transcript text starting from a list row. Cloud rows
 *  fetch the full conversation and build from its segments; local rows read the
 *  stored transcript string. The open detail view already holds this data — this
 *  loader is only for surfaces (the row context menu) acting on a row without
 *  opening it. */
export async function loadRowTranscript(row: ConversationRow): Promise<string> {
  if (row.source === 'local') {
    const c = await window.omi.getLocalConversation(row.id)
    return c?.transcript ?? ''
  }
  const r = await omiApi.get<Conversation>(`/v1/conversations/${row.id}`)
  return buildTranscriptText(r.data.transcript_segments ?? [])
}
