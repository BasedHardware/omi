import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { CONTEXT_BUCKET_SCHEMA } from '../../ipc/contextBucketSchema'
import {
  finalizeVisitOn,
  startVisitOn,
  writeExtractionOn,
  type ContextBucketDb,
  type ContextVisitFence
} from '../../ipc/contextBucketStore'
import { insertCandidateOn } from '../../ipc/proactivityLedger'
import {
  ContextProactivityEngine,
  frameMayGround,
  messagesAreDuplicates,
  type DirectorFrame,
  type EngineDeps,
  type PresentationOutcome
} from './engine'
import type { LaneClient, LaneRequest, LaneResult } from './laneClient'
import type { DeliveryGateInput } from './deliveryPolicy'

const T0 = 1_760_000_000_000

let db: ContextBucketDb
let nowMs: number
let epoch: number
let laneCalls: LaneRequest[]
let laneQueue: Array<LaneResult | Error>
let presented: Array<{ title: string; decisionType: string }>
let presentOutcome: PresentationOutcome
let dropInsteadOfPresent: boolean
let gate: DeliveryGateInput
let retrievalRuns: string[]
let graduationResult: { ok: true } | { ok: false; reason: string }

const laneResult = (content: unknown): LaneResult => ({
  content: JSON.stringify(content),
  providerModel: 'gpt-5.6-luna',
  cachedTokens: 10,
  cacheWriteTokens: 0,
  cacheWrite: false,
  fallbackClass: 'none'
})

const lane: LaneClient = {
  async complete(request) {
    laneCalls.push(request)
    const next = laneQueue.shift()
    if (next === undefined) throw new Error('lane queue empty')
    if (next instanceof Error) throw next
    return next
  },
  cooldownRemainingMs: () => 0,
  reset: () => {}
}

function makeDeps(over: Partial<EngineDeps> = {}): EngineDeps {
  return {
    db: () => db,
    lane,
    now: () => nowMs,
    sleep: async () => {},
    sessionEpoch: () => epoch,
    gateInput: () => gate,
    presentationPreflight: () => 'queued',
    present: (args) => {
      presented.push({ title: args.title, decisionType: args.decisionType })
      if (dropInsteadOfPresent) args.onDropped()
      else args.onPresented()
      return presentOutcome
    },
    trackedFrame: () => frame(),
    readFrameImage: async () => 'JPEGBASE64',
    incompleteTasks: () => [],
    retrievalHopEnabled: () => false,
    candidatesEnabled: () => false,
    runRetrieval: async (q: string) => {
      retrievalRuns.push(q)
      return {
        items: [{ ref: 'conversation:c1', title: 'Standup', preview: 'the demo', createdAt: '' }],
        allowedRefs: new Set(['conversation:c1'])
      }
    },
    graduate: async () => graduationResult,
    timeZone: 'America/Los_Angeles',
    ...over
  }
}

const frame = (over: Partial<DirectorFrame> = {}): DirectorFrame => ({
  frameId: 42,
  appName: 'Code',
  windowTitle: 'main.ts — omi',
  captureTime: nowMs,
  storedAt: nowMs,
  ...over
})

/** Seed a bucketed visit with one validated fact, leaving a fresh active visit. */
function seedEligibleVisit(): { fence: ContextVisitFence; entryId: string; factId: string } {
  const first = startVisitOn(db, {
    contextGeneration: 1,
    poolEpoch: 1,
    appName: 'Code',
    windowTitle: 'main.ts — omi',
    handles: [],
    processName: null,
    startedAt: T0
  })
  finalizeVisitOn(db, first, {
    outcome: 'completed',
    exitReason: 'context_switch',
    endedAt: T0 + 5_000,
    lastFrameId: null
  })
  const second = startVisitOn(db, {
    contextGeneration: 2,
    poolEpoch: 1,
    appName: 'Code',
    windowTitle: 'main.ts — omi',
    handles: [],
    processName: null,
    startedAt: T0 + 10_000
  })
  finalizeVisitOn(db, second, {
    outcome: 'completed',
    exitReason: 'context_switch',
    endedAt: T0 + 20_000,
    lastFrameId: 42
  })
  writeExtractionOn(
    db,
    second,
    {
      narrative: 'Working on the port.',
      facts: [
        {
          statement: 'Nik asked for the demo recording before launch.',
          identifiers: ['Nik'],
          evidence_text: 'Nik: need the demo recording',
          evidence_refs: [`visit:${second.visitID}`],
          confidence: 0.9,
          notify_worthiness: 0.8
        }
      ]
    },
    { appName: 'Code', windowTitle: 'main.ts — omi' },
    T0 + 21_000
  )
  const active = startVisitOn(db, {
    contextGeneration: 3,
    poolEpoch: 1,
    appName: 'Code',
    windowTitle: 'main.ts — omi',
    handles: [],
    processName: null,
    startedAt: T0 + 30_000
  })
  const entryId = (db.prepare(`SELECT id FROM bucket_entries LIMIT 1`).get() as { id: string }).id
  const factId = (
    db.prepare(`SELECT id FROM bucket_facts WHERE validityState='validated' LIMIT 1`).get() as {
      id: string
    }
  ).id
  return { fence: active, entryId, factId }
}

function deliveryRows(): Array<Record<string, unknown>> {
  return db
    .prepare(
      `SELECT decisionType, lifecycleState, provenanceJson, message FROM proactive_deliveries ORDER BY createdAt ASC`
    )
    .all() as Array<Record<string, unknown>>
}

const groundedDecision = (entryId: string, factId: string, over: Record<string, unknown> = {}) => ({
  decision: 'insight',
  title: 'Demo recording needed',
  message: 'Nik asked for the demo recording before launch.',
  reasoning: 'Grounded in a validated commitment.',
  bucket_entry_refs: [`entry:${entryId}`],
  fact_ids: [`fact:${factId}`],
  ...over
})

beforeEach(() => {
  db = new DatabaseSync(':memory:') as unknown as ContextBucketDb
  db.exec(CONTEXT_BUCKET_SCHEMA)
  nowMs = T0 + 31_000
  epoch = 1
  laneCalls = []
  laneQueue = []
  presented = []
  presentOutcome = 'presented'
  dropInsteadOfPresent = false
  retrievalRuns = []
  graduationResult = { ok: true }
  gate = {
    masterEnabled: true,
    frequencyLevel: 3,
    paywalled: false,
    cooldownMs: 0,
    dailyLimit: 40,
    lastGlobalPresentationAt: null
  }
})

describe('contextEntered', () => {
  it('runs the full happy path: settle, reserve, model, ground, present, delivered', async () => {
    const { fence, entryId, factId } = seedEligibleVisit()
    laneQueue = [laneResult(groundedDecision(entryId, factId))]
    const engine = new ContextProactivityEngine(makeDeps())

    await engine.contextEntered(fence)

    expect(presented).toEqual([{ title: 'Demo recording needed', decisionType: 'insight' }])
    const rows = deliveryRows()
    expect(rows.length).toBe(1)
    expect(rows[0].lifecycleState).toBe('delivered')
    expect(rows[0].decisionType).toBe('insight')
    const provenance = JSON.parse(rows[0].provenanceJson as string)
    expect(provenance.provider_model).toBe('gpt-5.6-luna')
    expect(provenance.bucket_entry_refs).toEqual([`entry:${entryId}`])
    expect(provenance.fact_ids).toEqual([`fact:${factId}`])
    // Provenance keys are sorted for byte-stable audit rows.
    expect(Object.keys(provenance)).toEqual([...Object.keys(provenance)].sort())
    // The settle mark landed on the visit row.
    const settled = db
      .prepare(`SELECT settledAt FROM context_visits WHERE id = ?`)
      .get(fence.visitID) as {
      settledAt: number | null
    }
    expect(settled.settledAt).not.toBeNull()
    // The lane call carried the stable/volatile split, image, and cache key.
    expect(laneCalls[0].cacheKey).toBe('director:v1')
    expect(laneCalls[0].imageBase64Jpeg).toBe('JPEGBASE64')
    expect(laneCalls[0].prompt).toContain('== BUCKET HEADER ==')
    expect(laneCalls[0].uncachedPrompt).toContain('== CURRENT FRAME METADATA ==')
  })

  it('rewrites ungrounded non-silence decisions to silence/suppressed without presenting', async () => {
    const { fence } = seedEligibleVisit()
    laneQueue = [
      laneResult({
        decision: 'insight',
        title: 't',
        message: 'm',
        reasoning: 'r',
        bucket_entry_refs: ['entry:bogus'],
        fact_ids: ['fact:bogus']
      })
    ]
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(fence)

    expect(presented).toEqual([])
    const rows = deliveryRows()
    expect(rows[0].decisionType).toBe('silence')
    expect(rows[0].lifecycleState).toBe('suppressed')
  })

  it('grounding demands BOTH sides: a valid entry ref with an invalid fact id still suppresses', async () => {
    const { fence, entryId } = seedEligibleVisit()
    laneQueue = [laneResult(groundedDecision(entryId, 'bogus'))]
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(fence)
    expect(presented).toEqual([])
    expect(deliveryRows()[0]).toMatchObject({
      decisionType: 'silence',
      lifecycleState: 'suppressed'
    })
  })

  it('a silence decision suppresses without spending fact validation or presenting', async () => {
    const { fence } = seedEligibleVisit()
    laneQueue = [
      laneResult({
        decision: 'silence',
        title: '',
        message: '',
        reasoning: 'nothing to add',
        bucket_entry_refs: [],
        fact_ids: []
      })
    ]
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(fence)
    expect(presented).toEqual([])
    expect(deliveryRows()[0]).toMatchObject({
      decisionType: 'silence',
      lifecycleState: 'suppressed'
    })
  })

  it('refuses a duplicate in-flight evaluation of the same visit', async () => {
    const { fence, entryId, factId } = seedEligibleVisit()
    laneQueue = [laneResult(groundedDecision(entryId, factId))]
    let release: () => void = () => {}
    const gatePromise = new Promise<void>((resolve) => {
      release = resolve
    })
    const engine = new ContextProactivityEngine(
      makeDeps({
        sleep: async () => {
          await gatePromise
        }
      })
    )
    const firstRun = engine.contextEntered(fence)
    const secondRun = engine.contextEntered(fence)
    release()
    await Promise.all([firstRun, secondRun])
    expect(laneCalls.length).toBe(1)
  })

  it('aborts before reserving when the session epoch changes during the settle sleep', async () => {
    const { fence } = seedEligibleVisit()
    const engine = new ContextProactivityEngine(
      makeDeps({
        sleep: async () => {
          epoch = 2
        }
      })
    )
    await engine.contextEntered(fence)
    expect(deliveryRows()).toEqual([])
    expect(laneCalls).toEqual([])
  })

  it('never evaluates ineligible snapshots or gated states', async () => {
    // No validated facts: eligible visit without extraction.
    const bare = startVisitOn(db, {
      contextGeneration: 1,
      poolEpoch: 1,
      appName: 'Code',
      windowTitle: 'main.ts — omi',
      handles: [],
      processName: null,
      startedAt: T0
    })
    finalizeVisitOn(db, bare, {
      outcome: 'completed',
      exitReason: 'context_switch',
      endedAt: T0 + 5_000,
      lastFrameId: null
    })
    const second = startVisitOn(db, {
      contextGeneration: 2,
      poolEpoch: 1,
      appName: 'Code',
      windowTitle: 'main.ts — omi',
      handles: [],
      processName: null,
      startedAt: T0 + 10_000
    })
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(second)
    expect(laneCalls).toEqual([])

    // Free-gate rejection: eligible snapshot, frequency off.
    const { fence } = seedEligibleVisit()
    gate = { ...gate, frequencyLevel: 0 }
    await engine.contextEntered(fence)
    expect(laneCalls).toEqual([])
    expect(deliveryRows()).toEqual([])
  })

  it('notification drop fails the row as notification_dropped', async () => {
    const { fence, entryId, factId } = seedEligibleVisit()
    laneQueue = [laneResult(groundedDecision(entryId, factId))]
    dropInsteadOfPresent = true
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(fence)
    const rows = deliveryRows()
    expect(rows[0].lifecycleState).toBe('failed')
    expect(rows[0].provenanceJson).toBe('{"failure":"notification_dropped"}')
  })

  it('lane failures terminalize the row with the bounded failure class', async () => {
    const { fence } = seedEligibleVisit()
    const { LaneError } = await import('./laneClient')
    laneQueue = [new LaneError('http_error', 'lane returned 500', 500)]
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(fence)
    const rows = deliveryRows()
    expect(rows[0]).toMatchObject({ decisionType: 'silence', lifecycleState: 'failed' })
    expect(JSON.parse(rows[0].provenanceJson as string)).toEqual({
      failure: 'http_error',
      status: 500
    })
  })
})

describe('the retrieval hop', () => {
  it('runs at most one hop, appends the section to the second call, and records cited refs', async () => {
    const { fence, entryId, factId } = seedEligibleVisit()
    laneQueue = [
      laneResult(
        groundedDecision(entryId, factId, { lookup_query: 'demo recording', decision: 'silence' })
      ),
      laneResult(
        groundedDecision(entryId, factId, {
          bucket_entry_refs: [`entry:${entryId}`, 'conversation:c1'],
          lookup_query: 'ignored second lookup'
        })
      )
    ]
    const engine = new ContextProactivityEngine(makeDeps({ retrievalHopEnabled: () => true }))
    await engine.contextEntered(fence)

    expect(retrievalRuns).toEqual(['demo recording'])
    expect(laneCalls.length).toBe(2)
    expect(laneCalls[1].uncachedPrompt).toContain('== RETRIEVED CONTEXT')
    expect(laneCalls[1].prompt).toBe(laneCalls[0].prompt)

    const rows = deliveryRows()
    expect(rows[0].lifecycleState).toBe('delivered')
    const provenance = JSON.parse(rows[0].provenanceJson as string)
    expect(provenance.retrieval).toMatchObject({
      query: 'demo recording',
      hop_completed: true,
      cited_refs: ['conversation:c1']
    })
    expect(provenance.bucket_entry_refs).toEqual([`entry:${entryId}`, 'conversation:c1'])
  })

  it('a failed hop keeps the first decision', async () => {
    const { fence, entryId, factId } = seedEligibleVisit()
    laneQueue = [laneResult(groundedDecision(entryId, factId, { lookup_query: 'demo recording' }))]
    const engine = new ContextProactivityEngine(
      makeDeps({
        retrievalHopEnabled: () => true,
        runRetrieval: async () => {
          throw new Error('search down')
        }
      })
    )
    await engine.contextEntered(fence)
    expect(deliveryRows()[0]).toMatchObject({
      decisionType: 'insight',
      lifecycleState: 'delivered'
    })
    expect(laneCalls.length).toBe(1)
  })
})

describe('task_candidate graduation', () => {
  it('graduation failure fails the row with the reason merged into provenance', async () => {
    const { fence, entryId, factId } = seedEligibleVisit()
    laneQueue = [laneResult(groundedDecision(entryId, factId, { decision: 'task_candidate' }))]
    graduationResult = { ok: false, reason: 'workflow_not_readable' }
    const engine = new ContextProactivityEngine(makeDeps())
    await engine.contextEntered(fence)
    expect(presented).toEqual([])
    const rows = deliveryRows()
    expect(rows[0].lifecycleState).toBe('failed')
    const provenance = JSON.parse(rows[0].provenanceJson as string)
    expect(provenance.failure).toBe('candidate_graduation_failed')
    expect(provenance.graduation_reason).toBe('workflow_not_readable')
  })
})

describe('the candidate fast path', () => {
  it('substitutes the gate call for the director, consumes on show, restores on drop', async () => {
    const { fence, factId } = seedEligibleVisit()
    const candidateId = insertCandidateOn(
      db,
      {
        bucketID: fence.bucketID as string,
        workstreamTag: null,
        message: 'Codemagic build 512 is still red after the pin bump.',
        groundingFactIDs: [factId],
        triggerNote: 'when back in the repo'
      },
      nowMs
    ) as string

    laneQueue = [laneResult({ show: true, reason: 'accurate and additive' })]
    const engine = new ContextProactivityEngine(makeDeps({ candidatesEnabled: () => true }))
    await engine.contextEntered(fence)

    // One decision per visit: the gate call replaced the director call.
    expect(laneCalls.length).toBe(1)
    expect(laneCalls[0].prompt).toContain('You are a yes/no delivery gate')
    expect(laneCalls[0].cacheKey).toBeUndefined()
    expect(presented.length).toBe(1)
    expect(deliveryRows()[0]).toMatchObject({
      decisionType: 'insight',
      lifecycleState: 'delivered'
    })
    const candidate = db
      .prepare(`SELECT state FROM proactive_candidates WHERE id = ?`)
      .get(candidateId) as {
      state: string
    }
    expect(candidate.state).toBe('consumed')
  })

  it('a declined gate suppresses without presenting and retires the candidate', async () => {
    const { fence, factId } = seedEligibleVisit()
    const candidateId = insertCandidateOn(
      db,
      {
        bucketID: fence.bucketID as string,
        workstreamTag: null,
        message: 'Old news candidate.',
        groundingFactIDs: [factId],
        triggerNote: 't'
      },
      nowMs
    ) as string
    laneQueue = [laneResult({ show: false, reason: 'already visible' })]
    const engine = new ContextProactivityEngine(makeDeps({ candidatesEnabled: () => true }))
    await engine.contextEntered(fence)

    expect(presented).toEqual([])
    expect(deliveryRows()[0]).toMatchObject({
      decisionType: 'silence',
      lifecycleState: 'suppressed'
    })
    const candidate = db
      .prepare(`SELECT expiresAt FROM proactive_candidates WHERE id = ?`)
      .get(candidateId) as {
      expiresAt: number
    }
    expect(candidate.expiresAt).toBeLessThanOrEqual(nowMs)
  })
})

describe('pure guards', () => {
  it('frameMayGround enforces capture bounds for live and departed visits', () => {
    const base = frame({ captureTime: T0 + 100, storedAt: T0 + 100 })
    expect(frameMayGround(base, T0, null)).toBe(true)
    expect(frameMayGround(frame({ captureTime: T0 - 1 }), T0, null)).toBe(false)
    expect(
      frameMayGround(frame({ captureTime: T0 + 500, storedAt: T0 + 500 }), T0, T0 + 1_000)
    ).toBe(true)
    expect(
      frameMayGround(frame({ captureTime: T0 + 2_500, storedAt: T0 + 900 }), T0, T0 + 1_000)
    ).toBe(true)
    expect(
      frameMayGround(frame({ captureTime: T0 + 3_500, storedAt: T0 + 900 }), T0, T0 + 1_000)
    ).toBe(false)
    expect(
      frameMayGround(frame({ captureTime: T0 + 500, storedAt: T0 + 1_500 }), T0, T0 + 1_000)
    ).toBe(false)
  })

  it('messagesAreDuplicates uses token-set Jaccard at 0.6', () => {
    expect(
      messagesAreDuplicates(
        'Codemagic build 512 is red after the pin bump',
        'the Codemagic build 512 is red after that pin bump'
      )
    ).toBe(true)
    expect(messagesAreDuplicates('Completely different topic here', 'Codemagic build red')).toBe(
      false
    )
    expect(messagesAreDuplicates('', 'anything')).toBe(false)
  })
})
