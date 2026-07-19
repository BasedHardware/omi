// Shared-thread agent cards (B4) — INV-CHAT-1.
//
// A background agent spawned from a chat/voice surface leaves EXACTLY TWO durable
// artifacts in that PRODUCING surface's shared thread: an `agentSpawn` card at
// launch and one `agentCompletion` card at terminal. Never live in-between
// chatter — those two writes are the whole contract.
//
// Faithful port of macOS' boundary (upstream FloatingControlBar/AgentPill.swift
// `recordPillTerminalCompletion` -> Chat/KernelTurnProjection.swift
// `appendAgentCompletion`, durability scanned by `hasMaterializedAgentCompletion`).
// DELIBERATE DEVIATION: macOS folds the `.agentSpawn`/`.agentCompletion` block
// INTO the producing assistant turn (its ChatProvider array carries blocks
// natively). Windows' renderer is text-only and reads a projection of the kernel
// store, so each card is its own conversation turn — the block rides `metadataJson`
// and a plain-text `content` marker keeps the text-only projections (context tail,
// backend echo) coherent. The invariant we port is the BOUNDARY (exactly two
// artifacts, no live chatter), not Mac's turn-nesting.
//
// The kernel `conversation_turns` table (omi-agentd.sqlite3) is the ONE
// authoritative transcript store (INV-CHAT-1 MUST-NOT #1). These helpers write
// and read cards THERE — no second store; the renderer projects from it.

import { randomUUID } from 'node:crypto'
import type { ChatContentBlock } from '../../shared/chatContent'
import type { AgentStore, ConversationTurn } from './types'
import { appendConversationTurn, listRecentConversationTurns } from './conversationTurns'

/** The two block kinds that ride a shared-thread agent card. */
export type AgentThreadCardBlock = Extract<
  ChatContentBlock,
  { type: 'agentSpawn' | 'agentCompletion' }
>

/** One materialized card, as read back for the renderer projection. */
export interface AgentThreadCardRecord {
  turnId: string
  createdAtMs: number
  block: AgentThreadCardBlock
}

/** A freshly-written card plus the chat id to broadcast it to (the producing
 *  surface's chat ref, matched against the renderer's active thread). */
export interface MaterializedAgentCard {
  record: AgentThreadCardRecord
  chatId: string | null
}

/** The stamp `spawn_agent` writes onto a background run's metadata so the terminal
 *  subscriber (which sees only sessionId/runId) can resolve the producing surface
 *  and title/objective long after the launch call returned. Namespaced under
 *  `omiAgentCard` so it never collides with other run metadata. */
export interface AgentCardStamp {
  producingConversationId: string
  /** The producing surface's chat id (session `externalRefId` when `externalRefKind
   *  === 'chat'`), used to match the renderer's active thread. Null for a producing
   *  surface with no chat ref. */
  producingChatId: string | null
  producingSurfaceKind: string
  pillId: string | null
  title: string
  objective: string
}

/** Metadata key the stamp lives under, inside a run's `inputJson.metadata`. */
export const AGENT_CARD_STAMP_KEY = 'omiAgentCard'

const AGENT_CARD_TURN_KIND = 'agentCard'

// Recent-turn scan window for idempotency + the renderer read. A producing
// conversation accrues at most two card turns per background run; 200 covers a
// long chat's worth of interleaved normal turns without an unbounded scan.
export const AGENT_CARD_SCAN_LIMIT = 200

interface AgentCardTurnMetadata {
  kind: typeof AGENT_CARD_TURN_KIND
  runId: string
  card: AgentThreadCardBlock
}

/** Build the `omiAgentCard`-namespaced metadata patch for a spawn. */
export function agentCardStampMetadata(stamp: AgentCardStamp): Record<string, unknown> {
  return { [AGENT_CARD_STAMP_KEY]: stamp }
}

/** Read the stamp back off a run's parsed `inputJson.metadata`, or null when the
 *  run was not spawned from a card-producing surface. */
export function readAgentCardStamp(metadata: unknown): AgentCardStamp | null {
  if (!metadata || typeof metadata !== 'object') return null
  const raw = (metadata as Record<string, unknown>)[AGENT_CARD_STAMP_KEY]
  if (!raw || typeof raw !== 'object') return null
  const s = raw as Record<string, unknown>
  if (typeof s.producingConversationId !== 'string' || !s.producingConversationId) return null
  return {
    producingConversationId: s.producingConversationId,
    producingChatId: typeof s.producingChatId === 'string' ? s.producingChatId : null,
    producingSurfaceKind:
      typeof s.producingSurfaceKind === 'string' ? s.producingSurfaceKind : 'main_chat',
    pillId: typeof s.pillId === 'string' ? s.pillId : null,
    title: typeof s.title === 'string' && s.title ? s.title : 'Background agent',
    objective: typeof s.objective === 'string' ? s.objective : ''
  }
}

/** Parse a conversation turn back into its card block, or null when the turn is a
 *  normal (non-card) turn. */
export function parseAgentCardTurn(
  turn: Pick<ConversationTurn, 'metadataJson'>
): AgentThreadCardBlock | null {
  try {
    const meta = JSON.parse(turn.metadataJson) as Partial<AgentCardTurnMetadata>
    const card = meta?.kind === AGENT_CARD_TURN_KIND ? meta.card : undefined
    if (card && (card.type === 'agentSpawn' || card.type === 'agentCompletion')) return card
  } catch {
    // Malformed / non-card metadata — treat as a normal turn.
  }
  return null
}

function findCardBlock(
  store: AgentStore,
  conversationId: string,
  predicate: (block: AgentThreadCardBlock) => boolean
): boolean {
  for (const turn of listRecentConversationTurns(store, conversationId, AGENT_CARD_SCAN_LIMIT)) {
    const card = parseAgentCardTurn(turn)
    if (card && predicate(card)) return true
  }
  return false
}

/** True when the producing conversation already carries the spawn card for `runId`. */
export function hasAgentSpawnCard(
  store: AgentStore,
  conversationId: string,
  runId: string
): boolean {
  return findCardBlock(store, conversationId, (b) => b.type === 'agentSpawn' && b.runId === runId)
}

/** True when the producing conversation already carries the completion card for
 *  `runId` — the exactly-one-completion idempotency guard (survives terminal
 *  retries and duplicate terminal events). */
export function hasAgentCompletionCard(
  store: AgentStore,
  conversationId: string,
  runId: string
): boolean {
  return findCardBlock(
    store,
    conversationId,
    (b) => b.type === 'agentCompletion' && b.runId === runId
  )
}

function appendCardTurn(
  store: AgentStore,
  input: {
    conversationId: string
    surfaceKind: string
    content: string
    block: AgentThreadCardBlock
    nowMs: number
  }
): AgentThreadCardRecord {
  const metadata: AgentCardTurnMetadata = {
    kind: AGENT_CARD_TURN_KIND,
    runId: input.block.runId ?? '',
    card: input.block
  }
  const turn = appendConversationTurn(store, {
    conversationId: input.conversationId,
    role: 'assistant',
    surfaceKind: input.surfaceKind,
    content: input.content,
    createdAtMs: input.nowMs,
    metadataJson: JSON.stringify(metadata)
  })
  return { turnId: turn.turnId, createdAtMs: turn.createdAtMs, block: input.block }
}

/** The run fields the completion card needs (a store-agnostic view of AgentRun). */
export interface AgentCardRunView {
  runId: string
  sessionId: string
  status: string
  finalText: string | null
  errorMessage: string | null
}

/** Normalize a kernel terminal run status to the card's display vocabulary. */
export function normalizeCompletionStatus(runStatus: string): 'succeeded' | 'stopped' | 'failed' {
  if (runStatus === 'succeeded') return 'succeeded'
  if (runStatus === 'cancelled') return 'stopped'
  return 'failed'
}

function completionStatusLabel(status: 'succeeded' | 'stopped' | 'failed'): string {
  return status === 'succeeded' ? 'finished' : status === 'stopped' ? 'was stopped' : 'failed'
}

const OUTPUT_MAX = 4000
const SNIPPET_MAX = 160

/** Write the launch (`agentSpawn`) card into the producing conversation, once.
 *  Idempotent: a repeat for the same runId is a no-op returning null. */
export function materializeAgentSpawnCard(
  store: AgentStore,
  input: { runId: string; sessionId: string; stamp: AgentCardStamp; nowMs: number }
): AgentThreadCardRecord | null {
  const { stamp } = input
  if (hasAgentSpawnCard(store, stamp.producingConversationId, input.runId)) return null
  const block: AgentThreadCardBlock = {
    type: 'agentSpawn',
    id: randomUUID(),
    ...(stamp.pillId ? { pillId: stamp.pillId } : {}),
    sessionId: input.sessionId,
    runId: input.runId,
    title: stamp.title,
    objective: stamp.objective
  }
  return appendCardTurn(store, {
    conversationId: stamp.producingConversationId,
    surfaceKind: stamp.producingSurfaceKind,
    content: `Started background agent: ${stamp.title}`,
    block,
    nowMs: input.nowMs
  })
}

/** Write the terminal (`agentCompletion`) card into the producing conversation,
 *  once. Idempotent on runId — exactly one completion even under terminal retry or
 *  a duplicate terminal event. */
export function materializeAgentCompletionCard(
  store: AgentStore,
  input: { run: AgentCardRunView; stamp: AgentCardStamp; nowMs: number }
): AgentThreadCardRecord | null {
  const { run, stamp } = input
  if (hasAgentCompletionCard(store, stamp.producingConversationId, run.runId)) return null
  const status = normalizeCompletionStatus(run.status)
  const output = ((status === 'succeeded' ? run.finalText : run.errorMessage) ?? '').slice(
    0,
    OUTPUT_MAX
  )
  const block: AgentThreadCardBlock = {
    type: 'agentCompletion',
    id: randomUUID(),
    ...(stamp.pillId ? { pillId: stamp.pillId } : {}),
    sessionId: run.sessionId,
    runId: run.runId,
    title: stamp.title,
    promptSnippet: stamp.objective.slice(0, SNIPPET_MAX),
    output,
    status
  }
  return appendCardTurn(store, {
    conversationId: stamp.producingConversationId,
    surfaceKind: stamp.producingSurfaceKind,
    content: `Background agent "${stamp.title}" ${completionStatusLabel(status)}`,
    block,
    nowMs: input.nowMs
  })
}

/** All cards in a conversation, oldest-first — the renderer projection read. */
export function listAgentThreadCards(
  store: AgentStore,
  conversationId: string,
  limit = AGENT_CARD_SCAN_LIMIT
): AgentThreadCardRecord[] {
  const out: AgentThreadCardRecord[] = []
  for (const turn of listRecentConversationTurns(store, conversationId, limit)) {
    const block = parseAgentCardTurn(turn)
    if (block) out.push({ turnId: turn.turnId, createdAtMs: turn.createdAtMs, block })
  }
  return out
}
