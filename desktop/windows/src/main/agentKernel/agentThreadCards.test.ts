// Tests for agentThreadCards.ts (B4, INV-CHAT-1). The one guarantee: a background
// agent spawned from a surface leaves EXACTLY TWO durable artifacts on that
// producing conversation — an agentSpawn card at launch and one agentCompletion
// card at terminal — idempotent under repeat + terminal retry, never live
// in-between chatter. Runs against the real store (node:sqlite seam).

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import { resolveSurfaceSession, type SurfaceRef } from './surfaceSession'
import { appendConversationTurn } from './conversationTurns'
import {
  agentCardStampMetadata,
  hasAgentCompletionCard,
  hasAgentSpawnCard,
  listAgentThreadCards,
  materializeAgentCompletionCard,
  materializeAgentSpawnCard,
  normalizeCompletionStatus,
  readAgentCardStamp,
  sweepOrphanedAgentCompletionCards,
  type AgentCardStamp
} from './agentThreadCards'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []

afterEach(() => {
  for (const store of openStores.splice(0)) {
    try {
      store.close()
    } catch {
      // already closed
    }
  }
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

function newStore(): SqliteAgentStore {
  const dir = mkdtempSync(join(tmpdir(), 'omi-cards-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3'),
    reconcileOnOpen: false
  })
  openStores.push(store)
  return store
}

const ref: SurfaceRef = {
  surfaceKind: 'main_chat',
  externalRefKind: 'chat',
  externalRefId: 'default'
}

function newConversation(store: SqliteAgentStore): string {
  return resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: ref }, () => 1000)
    .conversationId
}

function stampFor(conversationId: string): AgentCardStamp {
  return {
    producingConversationId: conversationId,
    producingChatId: 'default',
    producingSurfaceKind: 'main_chat',
    pillId: 'pill-1',
    title: 'Build X',
    objective: 'Build feature X end to end'
  }
}

describe('agent thread cards — the exactly-two boundary', () => {
  it('writes a spawn card at launch and one completion card at terminal', () => {
    const store = newStore()
    const conversationId = newConversation(store)
    const stamp = stampFor(conversationId)

    const spawn = materializeAgentSpawnCard(store, {
      runId: 'run_1',
      sessionId: 'sess_1',
      stamp,
      nowMs: 1000
    })
    const completion = materializeAgentCompletionCard(store, {
      run: {
        runId: 'run_1',
        sessionId: 'sess_1',
        status: 'succeeded',
        finalText: 'done',
        errorMessage: null
      },
      stamp,
      nowMs: 1001
    })

    expect(spawn?.block.type).toBe('agentSpawn')
    expect(completion?.block.type).toBe('agentCompletion')

    const cards = listAgentThreadCards(store, conversationId)
    expect(cards).toHaveLength(2)
    expect(cards.map((c) => c.block.type)).toEqual(['agentSpawn', 'agentCompletion'])
    expect(cards[0].block).toMatchObject({ runId: 'run_1', title: 'Build X', pillId: 'pill-1' })
    if (cards[1].block.type === 'agentCompletion') {
      expect(cards[1].block).toMatchObject({ runId: 'run_1', status: 'succeeded', output: 'done' })
    }
  })

  it('is idempotent: a repeat spawn and a retried terminal never add a second card', () => {
    const store = newStore()
    const conversationId = newConversation(store)
    const stamp = stampFor(conversationId)

    materializeAgentSpawnCard(store, { runId: 'run_1', sessionId: 'sess_1', stamp, nowMs: 1000 })
    // Duplicate spawn (e.g. a re-delivered run.queued) — no second card.
    const dupSpawn = materializeAgentSpawnCard(store, {
      runId: 'run_1',
      sessionId: 'sess_1',
      stamp,
      nowMs: 1002
    })
    expect(dupSpawn).toBeNull()

    const first = materializeAgentCompletionCard(store, {
      run: {
        runId: 'run_1',
        sessionId: 'sess_1',
        status: 'failed',
        finalText: null,
        errorMessage: 'boom'
      },
      stamp,
      nowMs: 1003
    })
    // Terminal retry / duplicate terminal event — exactly one completion.
    const retry = materializeAgentCompletionCard(store, {
      run: {
        runId: 'run_1',
        sessionId: 'sess_1',
        status: 'failed',
        finalText: null,
        errorMessage: 'boom again'
      },
      stamp,
      nowMs: 1004
    })
    expect(first?.block.type).toBe('agentCompletion')
    expect(retry).toBeNull()

    expect(listAgentThreadCards(store, conversationId)).toHaveLength(2)
    expect(hasAgentSpawnCard(store, conversationId, 'run_1')).toBe(true)
    expect(hasAgentCompletionCard(store, conversationId, 'run_1')).toBe(true)
  })

  it('keeps exactly two cards even with normal turns interleaved between launch and terminal', () => {
    const store = newStore()
    const conversationId = newConversation(store)
    const stamp = stampFor(conversationId)

    materializeAgentSpawnCard(store, { runId: 'run_1', sessionId: 'sess_1', stamp, nowMs: 1000 })
    // A normal user + assistant exchange lands between the two card writes — no
    // live agent chatter is a card; only the two markers are.
    appendConversationTurn(store, {
      conversationId,
      role: 'user',
      surfaceKind: 'main_chat',
      content: 'how is it going?',
      createdAtMs: 1001,
      metadataJson: JSON.stringify({ runId: 'run_x' })
    })
    appendConversationTurn(store, {
      conversationId,
      role: 'assistant',
      surfaceKind: 'main_chat',
      content: 'still working on it',
      createdAtMs: 1002,
      metadataJson: JSON.stringify({ runId: 'run_x' })
    })
    materializeAgentCompletionCard(store, {
      run: {
        runId: 'run_1',
        sessionId: 'sess_1',
        status: 'cancelled',
        finalText: null,
        errorMessage: null
      },
      stamp,
      nowMs: 1003
    })

    const cards = listAgentThreadCards(store, conversationId)
    expect(cards).toHaveLength(2)
    expect(cards.map((c) => c.block.type)).toEqual(['agentSpawn', 'agentCompletion'])
    if (cards[1].block.type === 'agentCompletion') {
      expect(cards[1].block.status).toBe('stopped') // cancelled → stopped
    }
  })

  it('maps terminal status to the card vocabulary and picks the right output source', () => {
    expect(normalizeCompletionStatus('succeeded')).toBe('succeeded')
    expect(normalizeCompletionStatus('cancelled')).toBe('stopped')
    expect(normalizeCompletionStatus('failed')).toBe('failed')
    expect(normalizeCompletionStatus('timedOut')).toBe('failed')

    const store = newStore()
    const conversationId = newConversation(store)
    const stamp = stampFor(conversationId)
    const completion = materializeAgentCompletionCard(store, {
      run: {
        runId: 'run_1',
        sessionId: 'sess_1',
        status: 'failed',
        finalText: 'partial',
        errorMessage: 'the reason'
      },
      stamp,
      nowMs: 1000
    })
    // A failed run shows the error, not the partial final text.
    if (completion?.block.type === 'agentCompletion') {
      expect(completion.block.output).toBe('the reason')
    }
  })

  it('round-trips the producing-surface stamp through run metadata', () => {
    const stamp = stampFor('conv_abc')
    const metadata = agentCardStampMetadata(stamp)
    // The stamp lives under a namespaced key inside a run's inputJson.metadata.
    const readBack = readAgentCardStamp(metadata)
    expect(readBack).toEqual(stamp)
    // A run with no stamp (a trusted-direct-control spawn with no originating chat)
    // resolves to null → no shared-thread cards.
    expect(readAgentCardStamp(undefined)).toBeNull()
    expect(readAgentCardStamp({ visible: true })).toBeNull()
  })
})

describe('agent thread cards — orphan/terminal load-time sweep', () => {
  function seedRun(
    store: SqliteAgentStore,
    sessionId: string,
    stamp: AgentCardStamp,
    status: string
  ): string {
    const run = store.insertRun({
      sessionId,
      clientId: 'c',
      requestId: 'r',
      status: status as never,
      mode: 'act',
      inputJson: JSON.stringify({
        prompt: 'build X',
        systemPrompt: '',
        metadata: agentCardStampMetadata(stamp)
      })
    })
    return run.runId
  }

  it('heals a run that went terminal holding a spawn card but no completion card', () => {
    const store = newStore()
    const resolved = resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: ref }, () => 1000)
    const stamp = stampFor(resolved.conversationId)

    // A background run launched (spawn card written) then the app crashed / the run
    // was orphaned by startup reconciliation — terminal in the db, no completion card.
    const runId = seedRun(store, resolved.agentSessionId, stamp, 'orphaned')
    materializeAgentSpawnCard(store, {
      runId,
      sessionId: resolved.agentSessionId,
      stamp,
      nowMs: 1000
    })

    const healed = sweepOrphanedAgentCompletionCards(store, { nowMs: () => 2000 })
    expect(healed).toHaveLength(1)
    expect(healed[0].chatId).toBe('default')
    const block = healed[0].record.block
    expect(block.type).toBe('agentCompletion')
    if (block.type === 'agentCompletion') {
      expect(block.runId).toBe(runId)
      expect(block.status).toBe('failed') // orphaned → failed
      expect(block.output).toMatch(/interrupted/i) // clear reason, never an empty body
    }

    // Exactly two cards, and a second sweep heals nothing (idempotent).
    expect(listAgentThreadCards(store, resolved.conversationId).map((c) => c.block.type)).toEqual([
      'agentSpawn',
      'agentCompletion'
    ])
    expect(sweepOrphanedAgentCompletionCards(store, { nowMs: () => 3000 })).toHaveLength(0)
    expect(listAgentThreadCards(store, resolved.conversationId)).toHaveLength(2)
  })

  it('does NOT fabricate a completion for a terminal run that never got a spawn card', () => {
    const store = newStore()
    const resolved = resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: ref }, () => 1000)
    const stamp = stampFor(resolved.conversationId)
    // Terminal + stamped, but no spawn card was ever written → out of scope.
    seedRun(store, resolved.agentSessionId, stamp, 'failed')

    expect(sweepOrphanedAgentCompletionCards(store)).toHaveLength(0)
    expect(listAgentThreadCards(store, resolved.conversationId)).toHaveLength(0)
  })

  it('leaves a still-running card-producing run alone (only terminal runs are swept)', () => {
    const store = newStore()
    const resolved = resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: ref }, () => 1000)
    const stamp = stampFor(resolved.conversationId)
    const runId = seedRun(store, resolved.agentSessionId, stamp, 'running')
    materializeAgentSpawnCard(store, {
      runId,
      sessionId: resolved.agentSessionId,
      stamp,
      nowMs: 1000
    })

    expect(sweepOrphanedAgentCompletionCards(store)).toHaveLength(0)
    // Just the spawn card — the completion waits for a real terminal.
    expect(listAgentThreadCards(store, resolved.conversationId).map((c) => c.block.type)).toEqual([
      'agentSpawn'
    ])
  })
})
