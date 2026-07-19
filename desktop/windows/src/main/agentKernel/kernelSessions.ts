// KernelSessions — Windows port of the macOS agent runtime's kernel-sessions.ts
// (desktop/macos/agent/src/runtime/kernel-sessions.ts).
//
// The session/transcript surface: listing sessions, resolving a surface to its
// canonical agent session, recording and importing conversation turns, the voice
// seed context, owner-state teardown, and binding invalidation.
//
// INV-CHAT-1: these turn APIs are the one kernel-owned transcript store. Backend
// chat rows are a downstream projection of what lands here, never the reverse.

import { KernelArtifacts } from './kernelArtifacts'
import {
  clearOwnerSurfaceState,
  importLegacyMainChatSessions,
  mergeFloatingChatIntoMainChat,
  resolveSurfaceSession,
  type LegacyMainChatSessionEntry,
  type ResolveSurfaceSessionInput,
  type ResolveSurfaceSessionResult,
  type SurfaceRef
} from './surfaceSession'
import {
  clearOwnerMainChatTurns,
  conversationIdForSession,
  getMainChatTurnTail,
  importConversationTurnsForSurface,
  projectCrossSurfaceTurn,
  recordSurfaceTurn as persistSurfaceTurn,
  type ConversationTurnImportEntry,
  type RecordSurfaceTurnResult
} from './conversationTurns'
import {
  AGENT_CARD_SCAN_LIMIT,
  listAgentThreadCards,
  materializeAgentCompletionCard,
  materializeAgentSpawnCard,
  readAgentCardStamp,
  type AgentCardStamp,
  type AgentThreadCardRecord,
  type MaterializedAgentCard
} from './agentThreadCards'
import { getVoiceSeedContext, getVoiceSeedSnapshot } from './turnContext'
import { boundedLimit, parseJsonObject, placeholders, sessionFromRow } from './kernelSupport'
import type { AgentRun, AgentSession, ConversationTurn } from './types'
import type {
  InvalidateBindingsInput,
  InvalidateBindingsResult,
  KernelSessionSummary,
  ListSessionsInput,
  StaleProcessLocalBindingsInput,
  StaleProcessLocalBindingsResult
} from './kernelTypes'

export class KernelSessions extends KernelArtifacts {
  /**
   * The authority a session confers on its caller. `ownerId` is part of it
   * because the model-facing MCP bridge binds identity from here rather than
   * accepting it off the wire (see controlMcpBridge.ts).
   */
  executionPolicyForSession(
    sessionId: string
  ): Pick<AgentSession, 'ownerId' | 'executionRole' | 'providerBoundary' | 'defaultAdapterId'> {
    const session = this.readSession(sessionId)
    return {
      ownerId: session.ownerId,
      executionRole: session.executionRole,
      providerBoundary: session.providerBoundary,
      defaultAdapterId: session.defaultAdapterId
    }
  }

  executionPolicyForOwnedSession(
    sessionId: string,
    ownerId: string
  ): Pick<AgentSession, 'executionRole' | 'providerBoundary' | 'defaultAdapterId'> {
    const session = this.readSession(sessionId)
    this.assertSessionOwner(session, ownerId)
    return {
      executionRole: session.executionRole,
      providerBoundary: session.providerBoundary,
      defaultAdapterId: session.defaultAdapterId
    }
  }

  listSessions(input: ListSessionsInput = {}): KernelSessionSummary[] {
    const where: string[] = []
    const values: unknown[] = []
    if (input.ownerId) {
      where.push('owner_id = ?')
      values.push(input.ownerId)
    }
    if (input.status) {
      where.push('status = ?')
      values.push(input.status)
    }
    if (input.surfaceKind) {
      where.push('surface_kind = ?')
      values.push(input.surfaceKind)
    }
    if (input.beforeUpdatedAtMs !== undefined) {
      where.push('updated_at_ms < ?')
      values.push(input.beforeUpdatedAtMs)
    }
    const limit = boundedLimit(input.limit, 50, 200)
    const sessions = this.store
      .allRows(
        `SELECT * FROM sessions
         ${where.length ? `WHERE ${where.join(' AND ')}` : ''}
         ORDER BY last_activity_at_ms DESC, created_at_ms DESC
         LIMIT ?`,
        [...values, limit]
      )
      .map(sessionFromRow)

    return sessions.map((session) => ({
      session,
      latestRun: this.readLatestRunForSession(session.sessionId),
      activeRun: this.readActiveRunForSession(session.sessionId),
      adapterBindings: this.readBindingsForSession(session.sessionId)
    }))
  }

  resolveSurfaceSession(input: ResolveSurfaceSessionInput): ResolveSurfaceSessionResult {
    return resolveSurfaceSession(this.store, input, () => Date.now())
  }

  importLegacyMainChatSessions(input: {
    ownerId: string
    entries: LegacyMainChatSessionEntry[]
  }): number {
    return importLegacyMainChatSessions(this.store, input, () => Date.now())
  }

  mergeFloatingChatIntoMainChat(input: { ownerId: string; chatId?: string }): {
    mergedTurns: number
    removedFloatingMapping: boolean
  } {
    return mergeFloatingChatIntoMainChat(this.store, input, () => Date.now())
  }

  importConversationTurns(input: {
    ownerId: string
    surfaceRef: SurfaceRef
    turns: ConversationTurnImportEntry[]
  }): number {
    return importConversationTurnsForSurface(this.store, {
      ownerId: input.ownerId,
      surfaceRef: input.surfaceRef,
      turns: input.turns,
      nowMs: () => Date.now()
    })
  }

  recordSurfaceTurn(input: {
    ownerId: string
    surfaceRef: SurfaceRef
    userText: string
    assistantText: string
    origin: string
    interrupted?: boolean
    idempotencyKey?: string
  }): RecordSurfaceTurnResult {
    return this.withTransaction(() =>
      persistSurfaceTurn(this.store, {
        ...input,
        nowMs: Date.now()
      })
    )
  }

  getVoiceSeedContext(input: { conversationId: string }): string {
    return getVoiceSeedContext(this.store, input.conversationId)
  }

  getVoiceSeedSnapshot(input: { conversationId: string }): {
    context: string
    idempotencyKeys: string[]
  } {
    return getVoiceSeedSnapshot(this.store, input.conversationId)
  }

  getVoiceSeedContextForSurface(input: { ownerId: string; surfaceRef: SurfaceRef }): {
    conversationId: string
    context: string
    idempotencyKeys: string[]
  } {
    const resolved = resolveSurfaceSession(this.store, input, () => Date.now())
    const snapshot = getVoiceSeedSnapshot(this.store, resolved.conversationId)
    return {
      conversationId: resolved.conversationId,
      context: snapshot.context,
      idempotencyKeys: snapshot.idempotencyKeys
    }
  }

  /**
   * READ-ONLY voice continuity seed for the main_chat/chat/<chatId> conversation —
   * the same conversation typed chat reads (getMainChatTurnTail). Unlike
   * getVoiceSeedContextForSurface (which resolveSurfaceSession-creates the
   * conversation), this only reads: an absent conversation yields an empty seed, so
   * the renderer's per-turn seed refresh never writes to the store (INV-CHAT-1
   * read side). `maxTurns`/`maxCharacters` cap the window (voice uses a small
   * Mac-parity window distinct from the kernel default).
   */
  getVoiceSeedContextForMainChat(input: {
    ownerId: string
    chatId?: string
    maxTurns?: number
    maxCharacters?: number
  }): { conversationId: string | null; context: string; idempotencyKeys: string[] } {
    const { conversationId } = getMainChatTurnTail(this.store, input.ownerId, 1, input.chatId)
    if (!conversationId) return { conversationId: null, context: '', idempotencyKeys: [] }
    const snapshot = getVoiceSeedSnapshot(this.store, conversationId, {
      maxTurns: input.maxTurns,
      maxCharacters: input.maxCharacters
    })
    return {
      conversationId,
      context: snapshot.context,
      idempotencyKeys: snapshot.idempotencyKeys
    }
  }

  clearOwnerState(ownerId: string): { invalidatedBindingIds: string[] } {
    return clearOwnerSurfaceState(this.store, ownerId, () => Date.now())
  }

  clearOwnerMainChatTurns(
    ownerId: string,
    chatId = 'default'
  ): {
    conversationId: string | null
    deletedTurns: number
  } {
    return clearOwnerMainChatTurns(this.store, ownerId, chatId)
  }

  getMainChatTurnTail(
    ownerId: string,
    limit = 8,
    chatId = 'default'
  ): {
    conversationId: string | null
    turns: ConversationTurn[]
  } {
    return getMainChatTurnTail(this.store, ownerId, limit, chatId)
  }

  projectCrossSurfaceTurn(input: {
    ownerId: string
    targetSurfaceRef?: SurfaceRef
    userText: string
    assistantText: string
    origin: string
    idempotencyKey?: string
  }): RecordSurfaceTurnResult {
    return this.withTransaction(() =>
      projectCrossSurfaceTurn(this.store, {
        ...input,
        nowMs: Date.now()
      })
    )
  }

  // === Shared-thread agent cards (B4, INV-CHAT-1) ============================
  // Exactly two authoritative artifacts per background run land on the producing
  // surface's kernel conversation: an agentSpawn card at launch and one
  // agentCompletion card at terminal. See agentThreadCards.ts for the contract.

  /** The producing conversation for a caller session, or null when the session has
   *  no surface conversation. */
  conversationIdForSession(sessionId: string): string | null {
    return conversationIdForSession(this.store, sessionId)
  }

  /** Resolve the stamp inputs a spawn writes onto a background run so its terminal
   *  can find the producing surface. Null when the caller session has no surface
   *  conversation (e.g. trusted-direct-control spawns with no originating chat) —
   *  those simply get no shared-thread cards. */
  getProducingCardSurface(
    sessionId: string
  ): { conversationId: string; chatId: string | null; surfaceKind: string } | null {
    const conversationId = conversationIdForSession(this.store, sessionId)
    if (!conversationId) return null
    const session = this.readSession(sessionId)
    return {
      conversationId,
      chatId: session.externalRefKind === 'chat' ? session.externalRefId : null,
      surfaceKind: session.surfaceKind
    }
  }

  /** Materialize the launch card for a background run, once (idempotent on runId).
   *  Null when the run was not spawned from a card-producing surface or the card
   *  already exists. */
  materializeAgentSpawnCard(runId: string): MaterializedAgentCard | null {
    const carded = this.readCardRun(runId)
    if (!carded) return null
    const { run, stamp } = carded
    const record = this.withTransaction(() =>
      materializeAgentSpawnCard(this.store, {
        runId: run.runId,
        sessionId: run.sessionId,
        stamp,
        nowMs: Date.now()
      })
    )
    return record ? { record, chatId: stamp.producingChatId } : null
  }

  /** Materialize the terminal card for a background run, once (idempotent on runId
   *  — exactly one completion even under terminal retry / duplicate terminal
   *  event). Null when the run is not card-producing or the card already exists. */
  materializeAgentCompletionCard(runId: string): MaterializedAgentCard | null {
    const carded = this.readCardRun(runId)
    if (!carded) return null
    const { run, stamp } = carded
    const record = this.withTransaction(() =>
      materializeAgentCompletionCard(this.store, {
        run: {
          runId: run.runId,
          sessionId: run.sessionId,
          status: run.status,
          finalText: run.finalText,
          errorMessage: run.errorMessage
        },
        stamp,
        nowMs: Date.now()
      })
    )
    return record ? { record, chatId: stamp.producingChatId } : null
  }

  /** The shared-thread agent cards for a main_chat thread, oldest-first — the
   *  renderer projection read (survives a completion that landed while the chat UI
   *  window was closed). */
  listAgentThreadCardsForMainChat(ownerId: string, chatId = 'default'): AgentThreadCardRecord[] {
    const { conversationId } = getMainChatTurnTail(this.store, ownerId, 1, chatId)
    if (!conversationId) return []
    return listAgentThreadCards(this.store, conversationId, AGENT_CARD_SCAN_LIMIT)
  }

  private readCardRun(runId: string): { run: AgentRun; stamp: AgentCardStamp } | null {
    let run: AgentRun
    try {
      run = this.readRun(runId)
    } catch {
      return null
    }
    const metadata = (parseJsonObject(run.inputJson) as { metadata?: unknown }).metadata
    const stamp = readAgentCardStamp(metadata)
    return stamp ? { run, stamp } : null
  }

  invalidateBindings(input: InvalidateBindingsInput): InvalidateBindingsResult {
    const session = this.findExistingSession(input)
    const sessionIds = session ? [session.sessionId] : this.findInvalidationSessionIds(input)
    if (sessionIds.length === 0) {
      return { invalidatedBindingIds: [] }
    }

    const rows = this.store.allRows(
      `SELECT binding_id, session_id
       FROM adapter_bindings
       WHERE session_id IN (${placeholders(sessionIds.length)})
         AND status = ?
         ${input.adapterId ? 'AND adapter_id = ?' : ''}`,
      input.adapterId ? [...sessionIds, 'active', input.adapterId] : [...sessionIds, 'active']
    )
    const invalidatedBindingIds = rows.map((row) => String(row.binding_id))
    if (invalidatedBindingIds.length === 0) {
      return { sessionId: session?.sessionId, invalidatedBindingIds }
    }

    const now = Date.now()
    this.withTransaction(() => {
      for (const bindingId of invalidatedBindingIds) {
        this.updateBinding(bindingId, {
          status: 'invalid',
          invalidatedAtMs: now,
          updatedAtMs: now
        })
        this.appendEvent({
          sessionId: String(rows.find((row) => String(row.binding_id) === bindingId)?.session_id),
          runId: null,
          attemptId: null,
          type: 'binding.stale',
          payload: {
            bindingId,
            adapterId: input.adapterId,
            reason: input.reason ?? 'invalidate_session'
          }
        })
      }
    })

    return { sessionId: session?.sessionId, invalidatedBindingIds }
  }

  staleProcessLocalBindings(
    input: StaleProcessLocalBindingsInput
  ): StaleProcessLocalBindingsResult {
    const rows = this.store.allRows(
      `SELECT binding_id, session_id
       FROM adapter_bindings
       WHERE adapter_id = ?
         AND resume_fidelity = ?
         AND status = ?`,
      [input.adapterId, 'none', 'active']
    )
    const staleBindingIds = rows.map((row) => String(row.binding_id))
    if (staleBindingIds.length === 0) {
      return { staleBindingIds }
    }

    const now = Date.now()
    this.withTransaction(() => {
      for (const row of rows) {
        const bindingId = String(row.binding_id)
        this.updateBinding(bindingId, {
          status: 'stale',
          invalidatedAtMs: now,
          updatedAtMs: now
        })
        this.appendEvent({
          sessionId: String(row.session_id),
          runId: null,
          attemptId: null,
          type: 'binding.stale',
          payload: {
            bindingId,
            adapterId: input.adapterId,
            reason: input.reason
          }
        })
      }
    })

    return { staleBindingIds }
  }
}
