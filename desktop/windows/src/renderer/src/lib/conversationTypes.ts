export type CloudConversation = {
  id: string
  // Backend processing state. Only 'completed' conversations are eligible for
  // retention — a 'processing' one's transcript_segments may still be empty/partial.
  status?: string
  transcript_segments?: { text: string }[]
}

// The Conversations list merges rows from three stores with different ids:
//   - cloud:    real backend ids, readable via GET /v1/conversations/:id
//   - local:    `local-*` screen recordings + `chat-*` saved Omi chats, in SQLite
//   - pending:  `pending-*` optimistic placeholders shown the instant a live
//               conversation finalizes — they live ONLY in pageCache's in-memory
//               array (no cloud row, no DB row) until the backend's real one arrives.
// The detail view must NOT issue a cloud GET for local/pending ids — they don't
// exist cloud-side and the fetch 404s (the bug this classifier guards against).
export type ConversationIdKind = 'pending' | 'local' | 'cloud'

export function classifyConversationId(id: string): ConversationIdKind {
  if (id.startsWith('pending-')) return 'pending'
  if (id.startsWith('local-') || id.startsWith('chat-')) return 'local'
  return 'cloud'
}
