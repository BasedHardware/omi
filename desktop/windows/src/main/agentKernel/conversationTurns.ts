// Conversation-turn persistence — Windows port of the macOS agent runtime's
// conversation-turns.ts (desktop/macos/agent/src/runtime/conversation-turns.ts).
//
// The durable transcript behind every surface. Records user/assistant turns
// (idempotently, keyed on an optional idempotency key), backfills legacy
// transcripts, tracks per-binding delivery high-water marks, and projects a
// cross-surface turn into main chat.

import { generateAgentId } from './store'
import type { AgentStore, ConversationTurn, NewConversationTurn } from './types'
import type { SurfaceRef } from './surfaceSession'
import { resolveSurfaceSession } from './surfaceSession'

export const CONVERSATION_TURN_BACKFILL_LIMIT = 50
export const CONVERSATION_TRANSCRIPT_TAIL_LIMIT = 10

export interface ConversationTurnImportEntry {
  role: 'user' | 'assistant'
  content: string
  surfaceKind?: string
  createdAtMs?: number
  metadataJson?: string
}

export function conversationIdForSession(store: AgentStore, sessionId: string): string | null {
  const row = store.getOptionalRow(
    `SELECT conversation_id FROM surface_conversations
     WHERE agent_session_id = ?
     ORDER BY last_active_at_ms DESC
     LIMIT 1`,
    [sessionId]
  )
  return row ? String(row.conversation_id) : null
}

export function listRecentConversationTurns(
  store: AgentStore,
  conversationId: string,
  limit = CONVERSATION_TRANSCRIPT_TAIL_LIMIT
): ConversationTurn[] {
  return store
    .allRows(
      `SELECT conversation_id, turn_id, role, surface_kind, content, created_at_ms, metadata_json
       FROM conversation_turns
       WHERE conversation_id = ?
       ORDER BY created_at_ms DESC
       LIMIT ?`,
      [conversationId, limit]
    )
    .map(conversationTurnFromRow)
    .reverse()
}

export function maxConversationTurnCreatedAtMs(store: AgentStore, conversationId: string): number {
  const row = store.getOptionalRow(
    'SELECT COALESCE(MAX(created_at_ms), 0) AS max_ms FROM conversation_turns WHERE conversation_id = ?',
    [conversationId]
  )
  return Number(row?.max_ms ?? 0)
}

export function listUndeliveredConversationTurns(
  store: AgentStore,
  conversationId: string,
  afterCreatedAtMs: number,
  limit = CONVERSATION_TRANSCRIPT_TAIL_LIMIT
): ConversationTurn[] {
  return store
    .allRows(
      `SELECT conversation_id, turn_id, role, surface_kind, content, created_at_ms, metadata_json
       FROM conversation_turns
       WHERE conversation_id = ? AND created_at_ms > ?
       ORDER BY created_at_ms ASC
       LIMIT ?`,
      [conversationId, afterCreatedAtMs, limit]
    )
    .map(conversationTurnFromRow)
}

export function advanceBindingTurnDelivery(
  store: AgentStore,
  bindingId: string,
  conversationId: string,
  nowMs?: number
): void {
  const maxMs = maxConversationTurnCreatedAtMs(store, conversationId)
  store.execute(
    `UPDATE adapter_bindings
     SET last_delivered_turn_created_at_ms = ?, updated_at_ms = ?
     WHERE binding_id = ?`,
    [maxMs, nowMs ?? Date.now(), bindingId]
  )
}

export function appendConversationTurn(
  store: AgentStore,
  input: NewConversationTurn
): ConversationTurn {
  return store.insertConversationTurn(input)
}

export interface RecordSurfaceTurnInput {
  ownerId: string
  surfaceRef: SurfaceRef
  userText: string
  assistantText: string
  origin: string
  interrupted?: boolean
  idempotencyKey?: string
  nowMs?: number
}

export interface RecordSurfaceTurnResult {
  conversationId: string
  recorded: boolean
  duplicate: boolean
  userTurn?: ConversationTurn
  assistantTurn?: ConversationTurn
}

export function recordSurfaceTurn(
  store: AgentStore,
  input: RecordSurfaceTurnInput
): RecordSurfaceTurnResult {
  const resolved = resolveSurfaceSession(
    store,
    { ownerId: input.ownerId, surfaceRef: input.surfaceRef },
    () => input.nowMs ?? Date.now()
  )
  const conversationId = resolved.conversationId
  const user = input.userText.trim()
  const assistant = input.assistantText.trim()
  if (!user && !assistant) {
    return { conversationId, recorded: false, duplicate: false }
  }

  const idempotencyKey = input.idempotencyKey?.trim()
  if (idempotencyKey && hasSurfaceTurnIdempotencyKey(store, conversationId, idempotencyKey)) {
    return { conversationId, recorded: false, duplicate: true }
  }

  const now = input.nowMs ?? Date.now()
  const baseMetadata = {
    origin: input.origin,
    interrupted: input.interrupted === true,
    ...(idempotencyKey ? { idempotencyKey } : {})
  }
  let userTurn: ConversationTurn | undefined
  let assistantTurn: ConversationTurn | undefined

  if (user) {
    userTurn = appendConversationTurn(store, {
      conversationId,
      role: 'user',
      surfaceKind: input.surfaceRef.surfaceKind,
      content: user,
      createdAtMs: now,
      metadataJson: JSON.stringify({ ...baseMetadata, role: 'user' })
    })
  }
  if (assistant) {
    assistantTurn = appendConversationTurn(store, {
      conversationId,
      role: 'assistant',
      surfaceKind: input.surfaceRef.surfaceKind,
      content: assistant,
      createdAtMs: now + 1,
      metadataJson: JSON.stringify({ ...baseMetadata, role: 'assistant' })
    })
  }

  return {
    conversationId,
    recorded: Boolean(userTurn || assistantTurn),
    duplicate: false,
    userTurn,
    assistantTurn
  }
}

function hasSurfaceTurnIdempotencyKey(
  store: AgentStore,
  conversationId: string,
  idempotencyKey: string
): boolean {
  const rows = store.allRows(
    `SELECT metadata_json
     FROM conversation_turns
     WHERE conversation_id = ?
     ORDER BY created_at_ms DESC
     LIMIT 32`,
    [conversationId]
  )
  for (const row of rows) {
    try {
      const metadata = JSON.parse(String(row.metadata_json ?? '{}')) as { idempotencyKey?: unknown }
      if (metadata.idempotencyKey === idempotencyKey) {
        return true
      }
    } catch {
      // ignore malformed metadata
    }
  }
  return false
}

export function importConversationTurnsBackfill(
  store: AgentStore,
  input: {
    conversationId: string
    turns: readonly ConversationTurnImportEntry[]
    nowMs: () => number
  }
): number {
  const existing = store.getOptionalRow(
    'SELECT 1 FROM conversation_turns WHERE conversation_id = ? LIMIT 1',
    [input.conversationId]
  )
  if (existing) return 0

  const bounded = input.turns
    .filter((turn) => turn.content.trim().length > 0)
    .slice(-CONVERSATION_TURN_BACKFILL_LIMIT)
  const now = input.nowMs()
  let imported = 0
  for (const [index, turn] of bounded.entries()) {
    store.insertConversationTurn({
      conversationId: input.conversationId,
      turnId: generateAgentId('turn'),
      role: turn.role,
      surfaceKind: turn.surfaceKind ?? 'main_chat',
      content: turn.content,
      createdAtMs: turn.createdAtMs ?? now - (bounded.length - index),
      metadataJson: turn.metadataJson ?? JSON.stringify({ source: 'swift_backfill' })
    })
    imported += 1
  }
  return imported
}

export function importConversationTurnsForSurface(
  store: AgentStore,
  input: {
    ownerId: string
    surfaceRef: SurfaceRef
    turns: readonly ConversationTurnImportEntry[]
    nowMs: () => number
  }
): number {
  const row = store.getOptionalRow(
    `SELECT conversation_id FROM surface_conversations
     WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
    [
      input.ownerId,
      input.surfaceRef.surfaceKind,
      input.surfaceRef.externalRefKind,
      input.surfaceRef.externalRefId
    ]
  )
  if (!row) return 0
  return importConversationTurnsBackfill(store, {
    conversationId: String(row.conversation_id),
    turns: input.turns,
    nowMs: input.nowMs
  })
}

function conversationTurnFromRow(row: Record<string, unknown>): ConversationTurn {
  return {
    conversationId: String(row.conversation_id),
    turnId: String(row.turn_id),
    role: String(row.role) as ConversationTurn['role'],
    surfaceKind: String(row.surface_kind),
    content: String(row.content),
    createdAtMs: Number(row.created_at_ms),
    metadataJson: String(row.metadata_json ?? '{}')
  }
}

const DEFAULT_MAIN_CHAT_SURFACE: SurfaceRef = {
  surfaceKind: 'main_chat',
  externalRefKind: 'chat',
  externalRefId: 'default'
}

function mainChatConversationId(
  store: AgentStore,
  ownerId: string,
  chatId = 'default'
): string | null {
  const row = store.getOptionalRow(
    `SELECT conversation_id FROM surface_conversations
     WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
    [ownerId, 'main_chat', 'chat', chatId]
  )
  return row ? String(row.conversation_id) : null
}

export function clearOwnerMainChatTurns(
  store: AgentStore,
  ownerId: string,
  chatId = 'default'
): { conversationId: string | null; deletedTurns: number } {
  const conversationId = mainChatConversationId(store, ownerId, chatId)
  if (!conversationId) {
    return { conversationId: null, deletedTurns: 0 }
  }
  const deletedTurns = store.execute(`DELETE FROM conversation_turns WHERE conversation_id = ?`, [
    conversationId
  ])
  return { conversationId, deletedTurns }
}

export function getMainChatTurnTail(
  store: AgentStore,
  ownerId: string,
  limit = 8,
  chatId = 'default'
): { conversationId: string | null; turns: ConversationTurn[] } {
  const conversationId = mainChatConversationId(store, ownerId, chatId)
  if (!conversationId) {
    return { conversationId: null, turns: [] }
  }
  return {
    conversationId,
    turns: listRecentConversationTurns(store, conversationId, limit)
  }
}

export function projectCrossSurfaceTurn(
  store: AgentStore,
  input: {
    ownerId: string
    targetSurfaceRef?: SurfaceRef
    userText: string
    assistantText: string
    origin: string
    idempotencyKey?: string
    nowMs?: number
  }
): RecordSurfaceTurnResult {
  return recordSurfaceTurn(store, {
    ownerId: input.ownerId,
    surfaceRef: input.targetSurfaceRef ?? DEFAULT_MAIN_CHAT_SURFACE,
    userText: input.userText,
    assistantText: input.assistantText,
    origin: input.origin,
    idempotencyKey: input.idempotencyKey,
    nowMs: input.nowMs
  })
}
