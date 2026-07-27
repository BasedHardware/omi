/** Wire format spoken with the local omi bridge over `ws://<host>/app`.
 *
 *  Control traffic is JSON with a `type` discriminator; the one binary channel
 *  is microphone PCM. Anything the bridge pushes that this build does not know
 *  is ignored rather than treated as an error, so a newer bridge can add
 *  message types without breaking an older app.
 *
 *  Dictating a question is a three-part exchange:
 *
 *    app -> bridge   {"type":"ask_start"}
 *    app -> bridge   binary frames, PCM16 LE / 16 kHz / mono
 *    app -> bridge   {"type":"ask_stop"}
 *    bridge -> app   {"type":"transcribed","text":...}  then chat_delta* + chat_done
 *    bridge -> app   {"type":"ask_error","text":...}    if it heard nothing
 *
 *  Binary frames sent *outside* an ask_start/ask_stop bracket mean something
 *  else entirely to the bridge — they are continuous-capture audio headed for a
 *  conversation — so the bracket has to be strict in both directions.
 */

export type ChatRequest = { type: 'chat'; text: string }
export type MemoriesRequest = { type: 'memories'; limit: number }
export type ActionItemsRequest = { type: 'action_items' }
export type TodayRequest = { type: 'today' }
export type AskStartRequest = { type: 'ask_start' }
export type AskStopRequest = { type: 'ask_stop' }

export type OutboundMessage =
  | ChatRequest
  | MemoriesRequest
  | ActionItemsRequest
  | TodayRequest
  | AskStartRequest
  | AskStopRequest

export type MemoryItem = { content: string }
export type ActionItem = { description: string; completed: boolean }

export type ChatDeltaMessage = { type: 'chat_delta'; text: string }
export type ChatDoneMessage = { type: 'chat_done'; text: string }
export type MemoriesMessage = { type: 'memories'; items: MemoryItem[] }
export type ActionItemsMessage = { type: 'action_items'; items: ActionItem[] }
export type TodayMessage = { type: 'today'; text: string }
export type PushMessage = { type: 'push'; text: string }
/** The bridge accepted `ask_start` and is now buffering PCM. Advisory — the
 *  glasses already say "Listening" by the time it lands. */
export type AskListeningMessage = { type: 'ask_listening' }
/** What the bridge heard, echoed back before the answer so a misheard question
 *  is obvious on the display instead of being guessed at from the answer. */
export type TranscribedMessage = { type: 'transcribed'; text: string }
/** The dictation failed: nothing audible, or transcription errored. Carries
 *  text meant to be shown to the user as-is. */
export type AskErrorMessage = { type: 'ask_error'; text: string }

export type InboundMessage =
  | ChatDeltaMessage
  | ChatDoneMessage
  | MemoriesMessage
  | ActionItemsMessage
  | TodayMessage
  | PushMessage
  | AskListeningMessage
  | TranscribedMessage
  | AskErrorMessage

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
    case 'ask_listening':
      return { type: 'ask_listening' }
    case 'transcribed':
      return typeof msg.text === 'string' ? { type: 'transcribed', text: msg.text } : null
    case 'ask_error':
      // Text is required: an error with nothing to show would leave the
      // display on "Thinking..." forever.
      return typeof msg.text === 'string' ? { type: 'ask_error', text: msg.text } : null
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
