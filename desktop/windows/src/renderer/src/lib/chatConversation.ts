import type { ChatMsg } from '../hooks/useChat'

export type ChatHistoryMode = 'per-launch' | 'infinite'

/** Injected accessor for the persisted infinite-conversation id (keeps this
 *  module pure / testable; the real impl reads localStorage). */
export type StoredId = {
  get: () => string | null
  set: (id: string) => void
}

/**
 * Resolve which conversation id a useChat instance should use.
 * - 'per-launch': a fresh id every call (new conversation per mount).
 * - 'infinite': one stable id, minted+stored on first use, shared thereafter.
 */
export function resolveChatId(
  mode: ChatHistoryMode,
  store: StoredId,
  mint: () => string
): string {
  if (mode === 'infinite') {
    const existing = store.get()
    if (existing) return existing
    const id = mint()
    store.set(id)
    return id
  }
  return mint()
}

/**
 * Merge an instance's `incoming` thread into the `stored` conversation by message
 * id. Stored order is preserved; an incoming message whose id already exists
 * REPLACES that entry in place (so a streamed assistant message updates rather
 * than duplicates), and incoming messages with a new id (or no id) are appended.
 * This lets the main window and the overlay write the same conversation without
 * either clobbering the other's messages.
 */
export function mergeChatMessages(stored: ChatMsg[], incoming: ChatMsg[]): ChatMsg[] {
  const out = [...stored]
  const indexById = new Map<string, number>()
  out.forEach((m, i) => {
    if (m.id) indexById.set(m.id, i)
  })
  for (const m of incoming) {
    const at = m.id != null ? indexById.get(m.id) : undefined
    if (at != null) {
      out[at] = m
    } else {
      if (m.id) indexById.set(m.id, out.length)
      out.push(m)
    }
  }
  return out
}
