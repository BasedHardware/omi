// Conversation-id classification.
//
// Conversation ids come from three sources and only ONE of them is safe to fetch
// from the server via `GET /v1/conversations/{id}`:
//   - `local-…`  → a recording stored only on this device (useRecording.ts)
//   - `chat-…`   → a local chat session with Omi (useChat.ts)
//   - `pending-…`→ an optimistic placeholder shown right after a recording is
//                  finalized, before the backend has produced the real cloud
//                  conversation (pageCache.ts). It has no server document yet.
// Everything else is a real server conversation id.
//
// The 404-on-open bug happened because `pending-…` ids leaked into the server
// fetch path (which assumed "not local ⇒ server"). Route every id through these
// helpers so a client-minted id can never hit the server detail endpoint.

export function isLocalConversationId(id: string): boolean {
  return id.startsWith('local-') || id.startsWith('chat-')
}

// Optimistic placeholder id — no server document exists yet.
export function isPendingConversationId(id: string): boolean {
  return id.startsWith('pending-')
}

// True only for ids that map to a real server conversation document, i.e. ids
// that are safe to fetch via `GET /v1/conversations/{id}`. Empty, local, and
// pending ids are all excluded.
export function isServerConversationId(id: string): boolean {
  return !!id && !isLocalConversationId(id) && !isPendingConversationId(id)
}
