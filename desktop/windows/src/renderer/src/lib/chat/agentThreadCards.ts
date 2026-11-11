// Renderer projection of shared-thread agent cards (B4, INV-CHAT-1).
//
// The two cards (agentSpawn at launch, one agentCompletion at terminal) are
// written authoritatively into the kernel conversation by main; the renderer
// reads them via `getAgentCardsForChat` on load and receives live `agentCardEvent`
// writes. Each card becomes an assistant ChatMsg carrying its block. These are
// NOT persisted back into the local-conversation store — they are re-projected
// from the kernel store on every load, so the kernel stays the single authority
// and the local store never drifts.

import type { AgentThreadCardMsg } from '../../../../shared/types'
import type { ChatMsg } from '../../hooks/useChat'

/** Wrap a card as an assistant ChatMsg. The block's id is the msg id, so a card
 *  seen both on load and via the live event de-dupes to one bubble. */
export function agentCardToChatMsg(card: AgentThreadCardMsg): ChatMsg {
  return { id: card.block.id, role: 'assistant', content: '', blocks: [card.block] }
}

/** Merge card messages into a thread, appending only cards not already present
 *  (by block id), oldest-first. Cards are the latest agent activity in the
 *  thread, so appending after existing history reads naturally. */
export function mergeAgentCards(history: ChatMsg[], cards: AgentThreadCardMsg[]): ChatMsg[] {
  const present = new Set(history.map((m) => m.id).filter((id): id is string => Boolean(id)))
  const additions = cards
    .filter((c) => !present.has(c.block.id))
    .sort((a, b) => a.createdAtMs - b.createdAtMs)
    .map(agentCardToChatMsg)
  return additions.length ? [...history, ...additions] : history
}
