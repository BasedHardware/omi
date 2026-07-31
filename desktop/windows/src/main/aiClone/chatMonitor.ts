// Track 2 (AI clone) — pure "what's new since we last looked" logic for one
// Beeper chat. No network, no fs, no Electron: this only decides which
// messages in an already-fetched batch are new inbound messages worth
// drafting a reply to. The IPC layer (ipc/aiClone.ts) owns fetching the batch
// from @beeper/desktop-api and persisting the returned cursor.
//
// Deliberately conservative on the very first look at a chat: rather than
// treating the chat's entire history as "new" the moment the user opts in
// (which would fire off a burst of drafts for old messages), the first poll
// only sets the cursor to "now" and drafts nothing. Only messages that arrive
// AFTER that point are ever surfaced.

/** Minimal shape this module needs from a Beeper message — decoupled from the
 *  SDK's full `Message` type so this stays pure and easy to test. `isSender`
 *  mirrors the real API's `Message.isSender` ("true if the authenticated user
 *  sent the message") — using it directly avoids needing to separately know
 *  and compare the account's own user id. */
export interface BeeperMessageLike {
  id: string
  isSender: boolean
  /** Epoch milliseconds (the real API's `timestamp` is an ISO string — the
   *  IPC layer converts it before calling in). */
  timestamp: number
  /** Absent/empty for non-text messages (attachments, reactions, etc.) —
   *  those are never drafted against. */
  text?: string | null
}

export interface NewInboundResult {
  /** New inbound (not-from-self, non-empty-text) messages, oldest first. */
  newMessages: BeeperMessageLike[]
  /** Cursor to persist for next time — the newest message's id, across ALL
   *  messages in the batch (including the user's own), so a poll never
   *  re-considers a message once it's been seen. Undefined when the batch
   *  was empty (nothing to advance the cursor to). */
  latestMessageId: string | undefined
  latestTimestamp: number | undefined
}

/**
 * Given a batch of messages for one chat, decide which are new inbound
 * messages worth drafting a reply to.
 *
 * @param messages     Recent messages for the chat (any order; sorted here).
 * @param lastSeenTimestamp  The persisted cursor from the previous poll, or
 *                     undefined on the very first poll for this chat.
 */
export function selectNewInboundMessages(
  messages: readonly BeeperMessageLike[],
  lastSeenTimestamp: number | undefined
): NewInboundResult {
  const sorted = [...messages].sort((a, b) => a.timestamp - b.timestamp)
  const newest = sorted[sorted.length - 1]
  const cursor = { latestMessageId: newest?.id, latestTimestamp: newest?.timestamp }

  if (lastSeenTimestamp === undefined) {
    // First-ever poll for this chat: establish the cursor, draft nothing
    // retroactively.
    return { newMessages: [], ...cursor }
  }

  const newMessages = sorted.filter(
    (m) =>
      m.timestamp > lastSeenTimestamp &&
      !m.isSender &&
      typeof m.text === 'string' &&
      m.text.trim().length > 0
  )
  return { newMessages, ...cursor }
}
