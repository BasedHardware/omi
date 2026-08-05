// Track 2 (AI clone) — thin wrapper around @beeper/desktop-api, the local
// REST API Beeper Desktop exposes (default http://localhost:23373) once the
// user is running Beeper Desktop and has pasted an access token generated in
// its own settings. This is deliberately the ONLY file that imports the SDK
// directly — everything else in aiClone/ (chatMonitor, autoReplyPolicy,
// personaDraftPrompt, the stores) is pure and adapter-agnostic, and ipc/aiClone.ts
// can therefore be tested against a fake BeeperClient instead of a real
// Beeper Desktop instance.
//
// Networks Beeper bridges (WhatsApp, Telegram, iMessage, Signal, etc.) all
// come through this one client — Beeper is the aggregation layer, so "connect
// Telegram and WhatsApp" is just "the user already added those accounts in
// Beeper Desktop," not a per-network integration Omi has to build.

import BeeperDesktop from '@beeper/desktop-api'

export interface BeeperAccountSummary {
  accountID: string
  network: string
  displayName: string
}

export interface BeeperChatSummary {
  chatID: string
  displayName: string
  network: string
  type: 'single' | 'group'
  lastActivity?: string
}

export interface BeeperMessageSummary {
  id: string
  isSender: boolean
  /** Epoch milliseconds — the SDK returns an ISO string; converted here so
   *  chatMonitor.ts (which works in epoch ms) stays SDK-agnostic. */
  timestamp: number
  text?: string | null
  senderID: string
}

export interface BeeperClient {
  /** Proves the token actually works and reports what's connected — used by
   *  both the Settings "Connect" flow and a background health check. Throws
   *  on a bad/expired token or an unreachable Beeper Desktop instance. */
  verifyConnection(): Promise<BeeperAccountSummary[]>
  /** Chats across every connected account, most recent activity first. */
  listChats(limit?: number): Promise<BeeperChatSummary[]>
  /** Recent messages for one chat. Best-effort recency — see the note above
   *  the implementation about `messages.list`'s ordering. */
  listRecentMessages(chatID: string, limit?: number): Promise<BeeperMessageSummary[]>
  sendMessage(chatID: string, text: string): Promise<void>
}

function toChatSummary(chat: {
  id: string
  title: string
  network: string
  type: 'single' | 'group'
  lastActivity?: string
}): BeeperChatSummary {
  return {
    chatID: chat.id,
    displayName: chat.title,
    network: chat.network,
    type: chat.type,
    lastActivity: chat.lastActivity
  }
}

function toMessageSummary(message: {
  id: string
  isSender?: boolean
  timestamp: string
  text?: string | null
  senderID: string
}): BeeperMessageSummary {
  return {
    id: message.id,
    isSender: Boolean(message.isSender),
    timestamp: Date.parse(message.timestamp),
    text: message.text,
    senderID: message.senderID
  }
}

/** Take up to `limit` items off an SDK auto-paginating async iterable without
 *  fetching more pages than needed. */
async function takeUpTo<T>(iterable: AsyncIterable<T>, limit: number): Promise<T[]> {
  const out: T[] = []
  for await (const item of iterable) {
    out.push(item)
    if (out.length >= limit) break
  }
  return out
}

export function createBeeperClient(accessToken: string): BeeperClient {
  const client = new BeeperDesktop({ accessToken })

  return {
    async verifyConnection() {
      const accounts = await client.accounts.list()
      return accounts.map((account) => ({
        accountID: account.accountID,
        network: account.network ?? account.bridge?.type ?? 'unknown',
        displayName: account.user?.fullName || account.user?.username || account.accountID
      }))
    },

    async listChats(limit = 30) {
      const page = await client.chats.search({ type: 'any', limit })
      const chats = await takeUpTo(page, limit)
      return chats.map(toChatSummary)
    },

    // NOTE: MessageListParams (unlike ChatSearchParams) has no `limit` field —
    // it's a plain cursor param, not a search param — so recency here relies
    // on the endpoint's documented "sorted by timestamp" default order plus
    // taking the first page. If a live Beeper Desktop instance turns out to
    // return oldest-first here, swap to client.messages.search({ chatIDs:
    // [chatID] }, which does support `limit` and is sorted for search, or add
    // an explicit `direction` once its accepted values are confirmed against
    // a running instance (no live Beeper Desktop is reachable from this
    // sandbox to verify empirically).
    async listRecentMessages(chatID, limit = 20) {
      const page = await client.messages.list(chatID)
      const messages = await takeUpTo(page, limit)
      return messages.map(toMessageSummary)
    },

    async sendMessage(chatID, text) {
      await client.messages.send(chatID, { text })
    }
  }
}
