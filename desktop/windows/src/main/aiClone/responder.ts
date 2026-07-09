// Pure decision core for the AI clone: given one incoming Beeper message plus
// the user's settings and the session state, decide whether to ignore it,
// queue a draft for approval, or auto-send a reply. No I/O — service.ts feeds
// it and acts on the result — so every rule here is directly unit-testable.
import type { AiCloneChatMode } from '../../shared/types'
import type { BeeperMessage } from './beeperClient'
import { beeperTimestampMs } from './beeperClient'

export type ResponderInput = {
  message: BeeperMessage
  chatType: 'single' | 'group'
  chatMode: AiCloneChatMode
  /** ms epoch when the responder started listening — older messages are history. */
  sessionStartedAt: number
  autoSentThisHour: number
  autoSendHourlyCap: number
}

export type ResponderDecision =
  | { action: 'ignore'; reason: string }
  | { action: 'draft' }
  | { action: 'autoSend' }

export const AUTO_SEND_HOURLY_CAP = 30

export function decide(input: ResponderInput): ResponderDecision {
  const { message, chatMode } = input
  if (chatMode === 'off') return { action: 'ignore', reason: 'chat_off' }
  if (message.isSender) return { action: 'ignore', reason: 'own_message' }
  if (message.isDeleted) return { action: 'ignore', reason: 'deleted' }
  if (!message.text?.trim()) return { action: 'ignore', reason: 'non_text' }

  const ts = beeperTimestampMs(message.timestamp)
  if (ts !== undefined && ts < input.sessionStartedAt) {
    return { action: 'ignore', reason: 'old_message' }
  }

  // v1 never auto-sends into group chats (too easy to misfire in front of an
  // audience) — an 'auto' group still gets a reviewable draft.
  if (chatMode === 'auto' && input.chatType === 'group') return { action: 'draft' }

  // Runaway guard: two bots replying to each other would loop forever. Past the
  // hourly cap, degrade to drafts instead of going silent.
  if (chatMode === 'auto' && input.autoSentThisHour >= input.autoSendHourlyCap) {
    return { action: 'draft' }
  }

  return chatMode === 'auto' ? { action: 'autoSend' } : { action: 'draft' }
}
