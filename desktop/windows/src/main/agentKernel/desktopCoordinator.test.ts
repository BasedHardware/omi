// Coordinator-surface contract tests: the context-packet security gates, the
// action-queue projection, and the intent-router decision order.
//
// These three are load-bearing beyond "it compiles":
//   - persistDesktopContextPacket is the gate that stops sensitive local context
//     (screenshots, rewind timeline, live screen) reaching a model without a
//     resolved user approval. It validates TWICE — once against the dispatch
//     ledger in the kernel, once structurally in the pure builder — and both
//     layers are asserted here independently.
//   - the action queue is a pure derivation whose ordering and suppression the
//     router depends on.
//   - the router's decision ORDER decides whether work resumes, forks, or blocks.
//
// Store driver: node:sqlite via the databaseFactory seam (see kernel.test.ts).

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from './kernel'
import { AdapterRegistry } from './adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import { buildDesktopActionQueue, type QueueRunInput } from './desktopActionQueue'
import { routeDesktopIntent } from './desktopIntentRouter'
import type { DesktopContextSnippetInput } from './desktopContextPacket'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const OWNER = 'owner-1'

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

function newKernel(): { kernel: AgentRuntimeKernel; store: SqliteAgentStore } {
  const dir = mkdtempSync(join(tmpdir(), 'omi-coordinator-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() })
  return { kernel, store }
}

function snippet(overrides: Partial<DesktopContextSnippetInput> = {}): DesktopContextSnippetInput {
  return {
    snippetId: 'snip-1',
    sourceKind: 'omi_db',
    operation: 'read_recent',
    provenance: { table: 'conversations' },
    content: 'benign local context',
    redactedContent: 'benign',
    sensitivityTier: 'local_private',
    ...overrides
  }
}

function packetInput(snippets: DesktopContextSnippetInput[]) {
  return {
    ownerId: OWNER,
    surfaceKind: 'main_chat',
    objective: 'summarize my day',
    snippets,
    retentionClass: 'ephemeral' as const,
    ttlMs: 15 * 60 * 1_000
  }
}

/** Seed an approval dispatch and resolve it with the given decision. */
function resolvedDispatch(
  store: SqliteAgentStore,
  input: {
    kind?: 'approval' | 'screen_context' | 'artifact_review'
    decision: 'allow' | 'deny'
    operation?: string | null
    resolve?: boolean
  }
): string {
  const dispatch = store.insertDesktopDispatch({
    ownerId: OWNER,
    kind: input.kind ?? 'approval',
    priority: 1,
    title: 'Share your screen with the agent?',
    decisionPrompt: 'Allow the agent to read the current screen?',
    operation: input.operation ?? null
  })
  if (input.resolve !== false) {
    store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: OWNER,
      status: 'resolved',
      resolvedBy: 'user',
      resolutionJson: JSON.stringify({ decision: input.decision })
    })
  }
  return dispatch.dispatchId
}

describe('persistDesktopContextPacket — dispatch ledger gate (kernel layer)', () => {
  it('persists an ordinary packet plus one access-log row per selected snippet', () => {
    const { kernel, store } = newKernel()

    const built = kernel.persistDesktopContextPacket(
      packetInput([snippet({ snippetId: 'a' }), snippet({ snippetId: 'b' })])
    )

    const packet = store.getRow('SELECT * FROM desktop_context_packets WHERE packet_id = ?', [
      built.packet.packetId
    ])
    expect(String(packet.owner_id)).toBe(OWNER)
    // Stored as JSON text, not [object Object].
    expect(JSON.parse(String(packet.packet_json)).objective).toBe('summarize my day')
    expect(JSON.parse(String(packet.redacted_preview_json)).snippets).toHaveLength(2)

    const logs = store.allRows('SELECT * FROM desktop_context_access_log WHERE packet_id = ?', [
      built.packet.packetId
    ])
    expect(logs).toHaveLength(2)
    expect(logs.every((log) => String(log.policy_decision) === 'allowed')).toBe(true)
  })

  it('refuses a sensitive snippet with no dispatch id at all', () => {
    const { kernel } = newKernel()

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([snippet({ sourceKind: 'screenshot_image', sensitivityTier: 'sensitive' })])
      )
    ).toThrow(/requires a dispatch id/)
  })

  it('refuses a sensitive snippet whose dispatch does not exist for this owner', () => {
    const { kernel } = newKernel()

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            sourceKind: 'rewind_timeline',
            sensitivityTier: 'sensitive',
            policyDecision: 'dispatch_created',
            dispatchId: 'ctx-does-not-exist'
          })
        ])
      )
    ).toThrow(/was not found for owner/)
  })

  it('refuses a sensitive snippet whose dispatch is still pending', () => {
    const { kernel, store } = newKernel()
    const dispatchId = resolvedDispatch(store, { decision: 'allow', resolve: false })

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            sourceKind: 'screen_current',
            sensitivityTier: 'high',
            policyDecision: 'dispatch_created',
            dispatchId
          })
        ])
      )
    ).toThrow(/is not approved/)
  })

  it('refuses a sensitive snippet whose dispatch was resolved with a deny', () => {
    const { kernel, store } = newKernel()
    const dispatchId = resolvedDispatch(store, { decision: 'deny' })

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            sourceKind: 'screenshot_image',
            sensitivityTier: 'sensitive',
            policyDecision: 'dispatch_created',
            dispatchId
          })
        ])
      )
    ).toThrow(/is not approved/)
  })

  it('refuses a dispatch of the wrong kind', () => {
    const { kernel, store } = newKernel()
    const dispatchId = resolvedDispatch(store, { kind: 'artifact_review', decision: 'allow' })

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            sourceKind: 'screenshot_image',
            sensitivityTier: 'sensitive',
            policyDecision: 'dispatch_created',
            dispatchId
          })
        ])
      )
    ).toThrow(/has invalid kind/)
  })

  it('refuses when the approved operation does not match the snippet operation', () => {
    const { kernel, store } = newKernel()
    const dispatchId = resolvedDispatch(store, {
      kind: 'screen_context',
      decision: 'allow',
      operation: 'read_screen'
    })

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            sourceKind: 'screen_current',
            operation: 'capture_screenshot',
            sensitivityTier: 'high',
            policyDecision: 'dispatch_created',
            dispatchId
          })
        ])
      )
    ).toThrow(/operation does not match snippet/)
  })

  it('admits a sensitive snippet backed by a resolved allow dispatch, logging the decision', () => {
    const { kernel, store } = newKernel()
    const dispatchId = resolvedDispatch(store, {
      kind: 'screen_context',
      decision: 'allow',
      operation: 'read_screen'
    })

    const built = kernel.persistDesktopContextPacket(
      packetInput([
        snippet({
          snippetId: 'screen',
          sourceKind: 'screen_current',
          operation: 'read_screen',
          sensitivityTier: 'high',
          policyDecision: 'dispatch_created',
          dispatchId,
          content: 'the user is looking at a spreadsheet',
          redactedContent: '[screen summary]'
        })
      ])
    )

    const log = store.getRow('SELECT * FROM desktop_context_access_log WHERE packet_id = ?', [
      built.packet.packetId
    ])
    expect(String(log.policy_decision)).toBe('dispatch_created')
    expect(String(log.dispatch_id)).toBe(dispatchId)
    // The redacted preview must never carry the raw content.
    expect(JSON.stringify(built.packet.redactedPreviewJson)).not.toContain('spreadsheet')
  })

  it('does not gate an unselected sensitive snippet, and leaves it out of the packet', () => {
    const { kernel, store } = newKernel()

    const built = kernel.persistDesktopContextPacket(
      packetInput([
        snippet({ snippetId: 'kept' }),
        snippet({
          snippetId: 'dropped',
          sourceKind: 'screenshot_image',
          sensitivityTier: 'sensitive',
          selected: false
        })
      ])
    )

    const logs = store.allRows('SELECT * FROM desktop_context_access_log WHERE packet_id = ?', [
      built.packet.packetId
    ])
    expect(logs).toHaveLength(1)
    expect(String(logs[0].source_kind)).toBe('omi_db')
  })
})

describe('persistDesktopContextPacket — structural gate (builder layer)', () => {
  // The builder re-validates independently of the dispatch ledger. Even a fully
  // approved snippet may not smuggle raw image bytes into the packet.
  it('rejects a data-URI image in snippet content even with an approved dispatch', () => {
    const { kernel, store } = newKernel()
    const dispatchId = resolvedDispatch(store, { kind: 'screen_context', decision: 'allow' })

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            sourceKind: 'screenshot_image',
            sensitivityTier: 'sensitive',
            policyDecision: 'dispatch_created',
            dispatchId,
            content: 'data:image/png;base64,iVBORw0KGgo='
          })
        ])
      )
    ).toThrow(/raw screenshot image bytes/)
  })

  it('rejects a base64-shaped blob hidden in a metadata value', () => {
    const { kernel } = newKernel()

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({
            metadata: { thumbnail: 'A'.repeat(500) }
          })
        ])
      )
    ).toThrow(/raw screenshot image bytes/)
  })

  it('requires a positive TTL', () => {
    const { kernel } = newKernel()

    expect(() =>
      kernel.persistDesktopContextPacket({ ...packetInput([snippet()]), ttlMs: 0 })
    ).toThrow(/positive TTL/)
  })

  it('writes nothing when validation fails mid-packet', () => {
    const { kernel, store } = newKernel()

    expect(() =>
      kernel.persistDesktopContextPacket(
        packetInput([
          snippet({ snippetId: 'ok' }),
          snippet({
            snippetId: 'bad',
            sourceKind: 'screenshot_image',
            sensitivityTier: 'sensitive'
          })
        ])
      )
    ).toThrow()

    expect(Number(store.getRow('SELECT COUNT(*) AS c FROM desktop_context_packets').c)).toBe(0)
    expect(Number(store.getRow('SELECT COUNT(*) AS c FROM desktop_context_access_log').c)).toBe(0)
  })
})

describe('buildDesktopActionQueue — ordering, suppression, dedup', () => {
  const NOW = 1_000_000_000

  function run(overrides: Partial<QueueRunInput> = {}): QueueRunInput {
    return {
      runId: 'run-1',
      sessionId: 'session-1',
      ownerId: OWNER,
      status: 'failed',
      title: 'Fix the exporter',
      goalText: 'fix the exporter pipeline',
      completedAtMs: NOW - 1_000,
      updatedAtMs: NOW - 1_000,
      createdAtMs: NOW - 5_000,
      ...overrides
    }
  }

  it('orders by rank asc, then priority desc, then createdAtMs desc', () => {
    const queue = buildDesktopActionQueue({
      nowMs: NOW,
      dispatches: [
        {
          dispatchId: 'd-low',
          ownerId: OWNER,
          kind: 'approval',
          status: 'pending',
          title: 'low',
          priority: 1,
          createdAtMs: NOW - 9_000
        },
        {
          dispatchId: 'd-high',
          ownerId: OWNER,
          kind: 'approval',
          status: 'pending',
          title: 'high',
          priority: 9,
          createdAtMs: NOW - 9_000
        }
      ],
      runs: [run()]
    })

    // rank 1 (dispatch) before rank 2 (failed_run); within rank, higher priority first.
    expect(queue.map((item) => item.kind)).toEqual(['dispatch', 'dispatch', 'failed_run'])
    expect(queue[0].subjectId).toBe('d-high')
    expect(queue[1].subjectId).toBe('d-low')
  })

  it('derives a deterministic itemId', () => {
    const queue = buildDesktopActionQueue({ nowMs: NOW, runs: [run()] })
    expect(queue[0].itemId).toBe('failed_run:run:run-1')
  })

  it('drops an expired dispatch', () => {
    const queue = buildDesktopActionQueue({
      nowMs: NOW,
      dispatches: [
        {
          dispatchId: 'd-expired',
          ownerId: OWNER,
          kind: 'approval',
          status: 'pending',
          title: 'expired',
          priority: 5,
          createdAtMs: NOW - 9_000,
          expiresAtMs: NOW - 1
        }
      ]
    })
    expect(queue).toHaveLength(0)
  })

  it('treats an active run as stale only past staleAfterMs (default 30 minutes)', () => {
    const fresh = buildDesktopActionQueue({
      nowMs: NOW,
      runs: [run({ status: 'running', updatedAtMs: NOW - 29 * 60_000 })]
    })
    expect(fresh).toHaveLength(0)

    const stale = buildDesktopActionQueue({
      nowMs: NOW,
      runs: [run({ status: 'running', updatedAtMs: NOW - 31 * 60_000 })]
    })
    expect(stale.map((item) => item.kind)).toEqual(['stale_run'])
  })

  it('suppresses a dismissed subject, and an override with a future hiddenUntil', () => {
    const overrides = [
      { ownerId: OWNER, subjectKind: 'run', subjectId: 'run-1', dismissedAtMs: NOW - 10 }
    ]
    expect(buildDesktopActionQueue({ nowMs: NOW, runs: [run()], overrides })).toHaveLength(0)

    const hidden = buildDesktopActionQueue({
      nowMs: NOW,
      runs: [run()],
      overrides: [
        { ownerId: OWNER, subjectKind: 'run', subjectId: 'run-1', hiddenUntilMs: NOW + 60_000 }
      ]
    })
    expect(hidden).toHaveLength(0)

    // An elapsed hiddenUntil no longer suppresses.
    const resurfaced = buildDesktopActionQueue({
      nowMs: NOW,
      runs: [run()],
      overrides: [
        { ownerId: OWNER, subjectKind: 'run', subjectId: 'run-1', hiddenUntilMs: NOW - 1 }
      ]
    })
    expect(resurfaced).toHaveLength(1)
  })

  it('applies suppression BEFORE the runItemLimit slice, so a hidden run cannot consume a slot', () => {
    const runs = [
      run({ runId: 'run-hidden', sessionId: 's1', updatedAtMs: NOW - 1_000 }),
      run({ runId: 'run-visible', sessionId: 's2', updatedAtMs: NOW - 2_000 })
    ]
    const queue = buildDesktopActionQueue({
      nowMs: NOW,
      runs,
      runItemLimit: 1,
      overrides: [
        { ownerId: OWNER, subjectKind: 'run', subjectId: 'run-hidden', dismissedAtMs: NOW - 10 }
      ]
    })

    // If suppression ran only on the final list, the limit-1 slice would have
    // taken run-hidden and the queue would be empty.
    expect(queue.map((item) => item.subjectId)).toEqual(['run-visible'])
  })

  it('hides a failed run that a newer successful run on the same goal already covers', () => {
    const failed = run({ runId: 'run-failed', completedAtMs: NOW - 10_000 })
    const succeeded = run({
      runId: 'run-succeeded',
      sessionId: 'session-2',
      status: 'succeeded',
      completedAtMs: NOW - 1_000,
      title: 'Fix the exporter',
      goalText: 'fix the exporter pipeline'
    })

    const covered = buildDesktopActionQueue({ nowMs: NOW, runs: [failed, succeeded] })
    expect(covered.some((item) => item.kind === 'failed_run')).toBe(false)

    // An unrelated success does not cover it.
    const unrelated = buildDesktopActionQueue({
      nowMs: NOW,
      runs: [
        failed,
        { ...succeeded, title: 'Draft the newsletter', goalText: 'draft the weekly newsletter' }
      ]
    })
    expect(unrelated.some((item) => item.kind === 'failed_run')).toBe(true)
  })
})

describe('routeDesktopIntent — decision order', () => {
  const NOW = 1_000_000_000

  const healthyCandidate = {
    sessionId: 'session-1',
    runId: 'run-1',
    surfaceKind: 'main_chat',
    taskId: null,
    title: 'Prior work',
    status: 'healthy' as const,
    relevance: 0.8,
    lastActivityAtMs: NOW - 1_000
  }

  const pendingDispatchItem = {
    itemId: 'dispatch:dispatch:d-1',
    kind: 'dispatch' as const,
    subjectKind: 'dispatch',
    subjectId: 'd-1',
    ownerId: OWNER,
    title: 'Approve screen access',
    priority: 101,
    rank: 1,
    createdAtMs: NOW - 1_000,
    reason: 'pending'
  }

  it('a pending dispatch outranks everything, even a resumable session', () => {
    const route = routeDesktopIntent({
      utterance: 'keep going on that',
      surfaceKind: 'main_chat',
      nowMs: NOW,
      actionQueue: [pendingDispatchItem],
      sessionCandidates: [healthyCandidate]
    })

    expect(route.intent).toBe('dispatch')
    expect(route.dispatchId).toBe('d-1')
    expect(route.queueItemId).toBe('dispatch:dispatch:d-1')
  })

  it('an ambiguous external send beats a resumable session', () => {
    const route = routeDesktopIntent({
      utterance: 'send this to the team',
      surfaceKind: 'main_chat',
      nowMs: NOW,
      sessionCandidates: [healthyCandidate]
    })
    expect(route.intent).toBe('dispatch')
  })

  it('an explicit draft-only send is not ambiguous', () => {
    const route = routeDesktopIntent({
      utterance: 'draft an email to the team, do not send',
      surfaceKind: 'main_chat',
      nowMs: NOW
    })
    expect(route.intent).not.toBe('dispatch')
  })

  it('a healthy candidate resumes; a stale/failed/orphaned one forks', () => {
    const resume = routeDesktopIntent({
      utterance: 'keep going',
      surfaceKind: 'main_chat',
      nowMs: NOW,
      sessionCandidates: [healthyCandidate]
    })
    expect(resume.intent).toBe('resume')
    expect(resume.sessionId).toBe('session-1')

    for (const status of ['stale', 'failed', 'orphaned'] as const) {
      const fork = routeDesktopIntent({
        utterance: 'keep going',
        surfaceKind: 'main_chat',
        nowMs: NOW,
        sessionCandidates: [{ ...healthyCandidate, status }]
      })
      expect(fork.intent).toBe('fork')
      expect(fork.sessionId).toBe('session-1')
    }
  })

  it('ignores a candidate below the 0.55 relevance floor', () => {
    const route = routeDesktopIntent({
      utterance: 'keep going',
      surfaceKind: 'main_chat',
      nowMs: NOW,
      sessionCandidates: [{ ...healthyCandidate, relevance: 0.54 }]
    })
    expect(route.intent).toBe('new_run')
  })

  it('does not resume a same-surface session for long-running new work', () => {
    const route = routeDesktopIntent({
      utterance: 'research the competitive landscape',
      surfaceKind: 'main_chat',
      nowMs: NOW,
      sessionCandidates: [healthyCandidate]
    })
    expect(route.intent).toBe('delegate')
  })

  it('falls through quick_answer, then delegate, then new_run', () => {
    expect(
      routeDesktopIntent({ utterance: 'list agents', surfaceKind: 'main_chat', nowMs: NOW }).intent
    ).toBe('quick_answer')
    expect(
      routeDesktopIntent({ utterance: 'refactor the parser', surfaceKind: 'main_chat', nowMs: NOW })
        .intent
    ).toBe('delegate')
    expect(
      routeDesktopIntent({ utterance: 'say hi', surfaceKind: 'main_chat', nowMs: NOW }).intent
    ).toBe('new_run')
  })
})
