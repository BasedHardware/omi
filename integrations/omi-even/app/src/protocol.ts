/** Wire format spoken with the local omi bridge over `ws://<host>/app`.
 *
 *  Everything is JSON with a `type` discriminator. The app only ever sends the
 *  four request shapes below; anything else the bridge pushes is ignored rather
 *  than treated as an error, so a newer bridge can add message types without
 *  breaking an older build of the app.
 */

export type ChatRequest = { type: 'chat'; text: string }
export type MemoriesRequest = { type: 'memories'; limit: number }
export type ActionItemsRequest = { type: 'action_items' }
export type TodayRequest = { type: 'today' }

export type OutboundMessage = ChatRequest | MemoriesRequest | ActionItemsRequest | TodayRequest

export type MemoryItem = { content: string }
export type ActionItem = { description: string; completed: boolean }

export type ChatDeltaMessage = { type: 'chat_delta'; text: string }
export type ChatDoneMessage = { type: 'chat_done'; text: string }
export type MemoriesMessage = { type: 'memories'; items: MemoryItem[] }
export type ActionItemsMessage = { type: 'action_items'; items: ActionItem[] }
export type TodayMessage = { type: 'today'; text: string }
export type PushMessage = { type: 'push'; text: string }

export type InboundMessage =
  | ChatDeltaMessage
  | ChatDoneMessage
  | MemoriesMessage
  | ActionItemsMessage
  | TodayMessage
  | PushMessage

/**
 * The `type` of a frame, or `null` if it is not even a JSON object. Used only
 * for logging: a bridge that speaks message types this build does not know
 * about should be diagnosable without being alarming.
 */
export function frameType(raw: string): string | null {
  try {
    const value = JSON.parse(raw) as unknown
    if (typeof value !== 'object' || value === null) return null
    const type = (value as Record<string, unknown>).type
    return typeof type === 'string' ? type : null
  } catch {
    return null
  }
}

/**
 * Parse a frame off the socket. Returns `null` for anything that is not a
 * recognised message so a malformed or future frame degrades to "ignored"
 * instead of throwing inside the socket callback.
 */
export function parseInbound(raw: string): InboundMessage | null {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof value !== 'object' || value === null) return null
  const msg = value as Record<string, unknown>

  switch (msg.type) {
    case 'chat_delta':
      return typeof msg.text === 'string' ? { type: 'chat_delta', text: msg.text } : null
    case 'chat_done':
      return typeof msg.text === 'string' ? { type: 'chat_done', text: msg.text } : null
    case 'today':
      return typeof msg.text === 'string' ? { type: 'today', text: msg.text } : null
    case 'push':
      return typeof msg.text === 'string' ? { type: 'push', text: msg.text } : null
    case 'memories': {
      if (!Array.isArray(msg.items)) return null
      const items: MemoryItem[] = []
      for (const item of msg.items) {
        const content = (item as Record<string, unknown> | null)?.content
        if (typeof content === 'string') items.push({ content })
      }
      return { type: 'memories', items }
    }
    case 'action_items': {
      if (!Array.isArray(msg.items)) return null
      const items: ActionItem[] = []
      for (const item of msg.items) {
        const record = item as Record<string, unknown> | null
        const description = record?.description
        if (typeof description === 'string') {
          items.push({ description, completed: record?.completed === true })
        }
      }
      return { type: 'action_items', items }
    }
    default:
      return null
  }
}
