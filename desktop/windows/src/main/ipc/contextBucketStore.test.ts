import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { CONTEXT_BUCKET_SCHEMA, CONTEXT_BUCKET_TABLE_NAMES } from './contextBucketSchema'
import {
  startVisitOn,
  finalizeVisitOn,
  markVisitSettledOn,
  reconcileInterruptedVisitsOn,
  visitFreshnessOn,
  snapshotForFenceOn,
  snapshotFactIdSet,
  validatedEntryRefsOn,
  validatedFactIDsOn,
  writeExtractionOn,
  applyDestinationOn,
  upsertExplicitBindingOn,
  lookupBindingOn,
  runDeterministicGCOn,
  referenceHashFor,
  type ContextBucketDb,
  type ContextVisitFence,
  type BucketExtraction
} from './contextBucketStore'

const T0 = 1_760_000_000_000
const DAY = 24 * 60 * 60 * 1000

let db: ContextBucketDb

beforeEach(() => {
  db = new DatabaseSync(':memory:') as unknown as ContextBucketDb
  db.exec(CONTEXT_BUCKET_SCHEMA)
})

function visit(over: Partial<Parameters<typeof startVisitOn>[1]> = {}): ContextVisitFence {
  return startVisitOn(db, {
    contextGeneration: 1,
    poolEpoch: 1,
    appName: 'Code',
    windowTitle: 'main.ts — omi',
    handles: [],
    processName: 'Code.exe',
    startedAt: T0,
    ...over
  })
}

/** Complete a full first+second visit cycle so the context earns a bucket. */
function bucketedVisit(title = 'main.ts — omi', app = 'Code'): ContextVisitFence {
  const first = visit({ windowTitle: title, appName: app, startedAt: T0 })
  finalizeVisitOn(db, first, {
    outcome: 'completed',
    exitReason: 'context_switch',
    endedAt: T0 + 5_000,
    lastFrameId: null
  })
  const second = visit({
    windowTitle: title,
    appName: app,
    startedAt: T0 + 10_000,
    contextGeneration: 2
  })
  expect(second.bucketID).not.toBeNull()
  return second
}

const extraction = (over: Partial<BucketExtraction> = {}): BucketExtraction => ({
  narrative: 'Working through the review notes.',
  facts: [
    {
      statement: 'Nik asked for the demo recording before the launch video.',
      identifiers: ['Nik'],
      evidence_text: 'Nik: need the demo recording before launch',
      evidence_refs: ['visit:VISIT'],
      confidence: 0.9,
      notify_worthiness: 0.8
    }
  ],
  ...over
})

function writeCompletedExtraction(
  fence: ContextVisitFence,
  ex: BucketExtraction,
  at = T0 + 20_000
) {
  finalizeVisitOn(db, fence, {
    outcome: 'completed',
    exitReason: 'context_switch',
    endedAt: at - 1,
    lastFrameId: 42
  })
  const resolved: BucketExtraction = {
    ...ex,
    facts: ex.facts.map((f) => ({
      ...f,
      evidence_refs: f.evidence_refs.map((r) => r.replace('VISIT', String(fence.visitID)))
    }))
  }
  return writeExtractionOn(
    db,
    fence,
    resolved,
    { appName: 'Code', windowTitle: 'main.ts — omi' },
    at
  )
}

describe('schema', () => {
  it('creates every canonical table', () => {
    for (const table of CONTEXT_BUCKET_TABLE_NAMES) {
      expect(
        db.prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name=?`).get(table)
      ).toBeTruthy()
    }
  })

  it('enforces NULL-safe subject uniqueness via the COALESCE index', () => {
    db.prepare(
      `INSERT INTO context_buckets (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
       VALUES ('b1', 'context', 's', NULL, 1, 1)`
    ).run()
    expect(() =>
      db
        .prepare(
          `INSERT INTO context_buckets (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt)
           VALUES ('b2', 'context', 's', NULL, 1, 1)`
        )
        .run()
    ).toThrow()
  })
})

describe('visit lifecycle and the second-visit gate', () => {
  it('gives blank titles an ephemeral hash and no bucket', () => {
    const fence = visit({ windowTitle: '   ' })
    expect(fence.bucketID).toBeNull()
    const row = db
      .prepare(`SELECT referenceHash FROM context_visits WHERE id = ?`)
      .get(fence.visitID) as {
      referenceHash: string
    }
    expect(row.referenceHash.startsWith('ephemeral:')).toBe(true)
  })

  it('a brand-new context gets no bucket on its first visit', () => {
    expect(visit().bucketID).toBeNull()
  })

  it('the bucket is born on the second qualifying visit and the binding starts at 2', () => {
    const fence = bucketedVisit()
    const binding = db
      .prepare(
        `SELECT occurrenceCount, source, confidence FROM subject_bindings WHERE bucketID = ?`
      )
      .get(fence.bucketID) as { occurrenceCount: number; source: string; confidence: number }
    expect(binding.occurrenceCount).toBe(2)
    expect(binding.source).toBe('repeat_cooccurrence')
    expect(binding.confidence).toBe(0.5)
  })

  it('a completed visit outside the 7-day window does not satisfy the gate', () => {
    const first = visit()
    finalizeVisitOn(db, first, {
      outcome: 'completed',
      exitReason: 'context_switch',
      endedAt: T0 + 1_000,
      lastFrameId: null
    })
    const later = visit({ startedAt: T0 + 8 * DAY, contextGeneration: 2 })
    expect(later.bucketID).toBeNull()
  })

  it('a discarded first visit does not satisfy the gate', () => {
    const first = visit()
    finalizeVisitOn(db, first, {
      outcome: 'discarded',
      exitReason: 'context_switch',
      endedAt: T0 + 300,
      lastFrameId: null
    })
    expect(visit({ startedAt: T0 + 10_000, contextGeneration: 2 }).bucketID).toBeNull()
  })

  it('later visits reuse the bucket via the binding without touching occurrenceCount', () => {
    const fence = bucketedVisit()
    const third = visit({ startedAt: T0 + 30_000, contextGeneration: 3 })
    expect(third.bucketID).toBe(fence.bucketID)
    // A consistent binding returns early in the resolver; the upsert (and its
    // occurrence bump) only runs on the re-resolve path.
    const binding = db
      .prepare(`SELECT occurrenceCount FROM subject_bindings WHERE bucketID = ?`)
      .get(fence.bucketID) as { occurrenceCount: number }
    expect(binding.occurrenceCount).toBe(2)
  })

  it('a pre-existing explicit binding skips the second-visit gate', () => {
    const key = referenceHashFor('code::first sight')
    upsertExplicitBindingOn(
      db,
      { referenceHash: key, subjectKind: 'task', subjectID: 't-1', workstreamID: null },
      T0
    )
    const fence = visit({ windowTitle: 'First Sight' })
    expect(fence.bucketID).not.toBeNull()
    const bucket = db
      .prepare(`SELECT subjectKind, subjectID FROM context_buckets WHERE id = ?`)
      .get(fence.bucketID) as { subjectKind: string; subjectID: string }
    expect(bucket).toEqual({ subjectKind: 'task', subjectID: 't-1' })
  })

  it('completed finalize increments visitCount and lastVisitedAt; discarded does not', () => {
    // The first (gated) visit was bucketless, so this completion is the
    // bucket's first counted visit.
    const fence = bucketedVisit()
    finalizeVisitOn(db, fence, {
      outcome: 'completed',
      exitReason: 'context_switch',
      endedAt: T0 + 60_000,
      lastFrameId: null
    })
    const bucket = db
      .prepare(`SELECT visitCount, lastVisitedAt FROM context_buckets WHERE id = ?`)
      .get(fence.bucketID) as { visitCount: number; lastVisitedAt: number }
    expect(bucket.visitCount).toBe(1)
    expect(bucket.lastVisitedAt).toBe(T0 + 60_000)
  })

  it('finalize is fence-guarded: wrong generation and double finalize both refuse', () => {
    const fence = visit()
    const wrongGen = { ...fence, contextGeneration: 99 }
    expect(
      finalizeVisitOn(db, wrongGen, {
        outcome: 'completed',
        exitReason: 'context_switch',
        endedAt: T0 + 1,
        lastFrameId: null
      })
    ).toBe(false)
    expect(
      finalizeVisitOn(db, fence, {
        outcome: 'completed',
        exitReason: 'context_switch',
        endedAt: T0 + 1,
        lastFrameId: null
      })
    ).toBe(true)
    expect(
      finalizeVisitOn(db, fence, {
        outcome: 'discarded',
        exitReason: 'context_switch',
        endedAt: T0 + 2,
        lastFrameId: null
      })
    ).toBe(false)
  })

  it('markVisitSettled is idempotent on the first settle time and stale after finalize', () => {
    const fence = visit()
    expect(markVisitSettledOn(db, fence, T0 + 2_000)).toBe(true)
    expect(markVisitSettledOn(db, fence, T0 + 9_000)).toBe(true)
    const row = db
      .prepare(`SELECT settledAt FROM context_visits WHERE id = ?`)
      .get(fence.visitID) as {
      settledAt: number
    }
    expect(row.settledAt).toBe(T0 + 2_000)
    finalizeVisitOn(db, fence, {
      outcome: 'completed',
      exitReason: 'context_switch',
      endedAt: T0 + 10_000,
      lastFrameId: null
    })
    expect(markVisitSettledOn(db, fence, T0 + 11_000)).toBe(false)
  })

  it('freshness: active fresh, completed fresh for 60s, interrupted never', () => {
    const fence = visit()
    expect(visitFreshnessOn(db, fence, T0 + 1_000).fresh).toBe(true)
    finalizeVisitOn(db, fence, {
      outcome: 'completed',
      exitReason: 'context_switch',
      endedAt: T0 + 5_000,
      lastFrameId: null
    })
    expect(visitFreshnessOn(db, fence, T0 + 64_000).fresh).toBe(true)
    expect(visitFreshnessOn(db, fence, T0 + 66_000).fresh).toBe(false)

    const second = visit({ contextGeneration: 2, startedAt: T0 + 70_000 })
    finalizeVisitOn(db, second, {
      outcome: 'interrupted',
      exitReason: 'system_sleep',
      endedAt: T0 + 71_000,
      lastFrameId: null
    })
    expect(visitFreshnessOn(db, second, T0 + 71_500).fresh).toBe(false)
  })

  it('startup reconcile interrupts leftover active visits', () => {
    visit()
    visit({ contextGeneration: 2, startedAt: T0 + 1_000 })
    expect(reconcileInterruptedVisitsOn(db, T0 + 5_000)).toBe(2)
    const outcomes = db
      .prepare(`SELECT DISTINCT outcome, exitReason FROM context_visits`)
      .all() as Array<{
      outcome: string
      exitReason: string
    }>
    expect(outcomes).toEqual([{ outcome: 'interrupted', exitReason: 'startup_reconcile' }])
  })
})

describe('extraction write', () => {
  it('refuses to land on a still-active visit', () => {
    const fence = bucketedVisit()
    expect(
      writeExtractionOn(db, fence, extraction(), { appName: 'Code', windowTitle: 't' }, T0 + 1_000)
    ).toBeNull()
  })

  it('writes the entry and a validated fact, updates bucket worthiness, publishes a version', () => {
    const fence = bucketedVisit()
    const result = writeCompletedExtraction(fence, extraction())
    expect(result).not.toBeNull()
    expect(result?.maximumValidatedWorthiness).toBe(0.8)

    const fact = db
      .prepare(`SELECT validityState, notifyWorthiness FROM bucket_facts WHERE bucketID = ?`)
      .get(fence.bucketID) as { validityState: string; notifyWorthiness: number }
    expect(fact.validityState).toBe('validated')
    expect(fact.notifyWorthiness).toBe(0.8)

    const bucket = db
      .prepare(`SELECT notifyWorthiness FROM context_buckets WHERE id = ?`)
      .get(fence.bucketID) as {
      notifyWorthiness: number
    }
    expect(bucket.notifyWorthiness).toBe(0.8)

    const entry = db
      .prepare(`SELECT bucketVersionID, evidenceRefsJson FROM bucket_entries WHERE bucketID = ?`)
      .get(fence.bucketID) as { bucketVersionID: number; evidenceRefsJson: string }
    expect(entry.bucketVersionID).toBe(result?.versionID)
    expect(JSON.parse(entry.evidenceRefsJson)).toEqual([`visit:${fence.visitID}`])
  })

  it('a fact without a surviving identifier or with out-of-allowlist refs is needs_review with zero worthiness', () => {
    const fence = bucketedVisit()
    const result = writeCompletedExtraction(
      fence,
      extraction({
        facts: [
          {
            statement: 'Something happened on screen.',
            identifiers: ['fact-12', 'not-in-evidence'],
            evidence_text: 'unrelated wording',
            evidence_refs: ['screenshot:999999'],
            confidence: 0.9,
            notify_worthiness: 0.9
          }
        ]
      })
    )
    expect(result?.maximumValidatedWorthiness).toBe(0)
    const fact = db
      .prepare(
        `SELECT validityState, notifyWorthiness, identifiersJson FROM bucket_facts WHERE bucketID = ?`
      )
      .get(fence.bucketID) as {
      validityState: string
      notifyWorthiness: number
      identifiersJson: string
    }
    expect(fact.validityState).toBe('needs_review')
    expect(fact.notifyWorthiness).toBe(0)
    expect(JSON.parse(fact.identifiersJson)).toEqual([])
  })

  it('scaffolding statements are skipped and duplicate statements become superseded', () => {
    const fence = bucketedVisit()
    writeCompletedExtraction(fence, extraction())
    const third = visit({ contextGeneration: 3, startedAt: T0 + 40_000 })
    const result = writeCompletedExtraction(
      third,
      extraction({
        facts: [
          {
            statement: 'Proposed record: skip me entirely.',
            identifiers: ['x'],
            evidence_text: 'x',
            evidence_refs: ['visit:VISIT'],
            confidence: 1,
            notify_worthiness: 1
          },
          {
            statement: 'Nik asked for the demo recording before the launch video.',
            identifiers: ['Nik'],
            evidence_text: 'Nik: need the demo recording before launch',
            evidence_refs: ['visit:VISIT'],
            confidence: 0.9,
            notify_worthiness: 0.8
          }
        ]
      }),
      T0 + 50_000
    )
    expect(result?.maximumValidatedWorthiness).toBe(0)
    const states = db
      .prepare(
        `SELECT validityState, COUNT(*) AS n FROM bucket_facts GROUP BY validityState ORDER BY validityState`
      )
      .all() as Array<{ validityState: string; n: number }>
    expect(states).toEqual([
      { validityState: 'superseded', n: 1 },
      { validityState: 'validated', n: 1 }
    ])
  })

  it('compacts to the frozen segment once more than five uncompacted entries exist', () => {
    const fence = bucketedVisit()
    let current = fence
    for (let i = 0; i < 6; i++) {
      writeCompletedExtraction(
        current,
        extraction({ narrative: `Narrative number ${i}.`, facts: [] }),
        T0 + 20_000 + i * 1_000
      )
      current = visit({ contextGeneration: 3 + i, startedAt: T0 + 30_000 + i * 1_000 })
    }
    const frozen = db
      .prepare(
        `SELECT frozenRankedSegment FROM bucket_versions WHERE bucketID = ? ORDER BY version DESC LIMIT 1`
      )
      .get(fence.bucketID) as { frozenRankedSegment: Uint8Array }
    const text = Buffer.from(frozen.frozenRankedSegment).toString('utf8')
    expect(text).toContain('- entry:')
    expect(text).toContain('Narrative number 0.')
    const uncompacted = db
      .prepare(`SELECT COUNT(*) AS n FROM bucket_entries WHERE bucketID = ? AND isCompacted = 0`)
      .get(fence.bucketID) as { n: number }
    expect(uncompacted.n).toBe(5)
  })
})

describe('snapshot and citation validation', () => {
  it('renders the tail chronologically and facts in the pinned format', () => {
    const fence = bucketedVisit()
    writeCompletedExtraction(fence, extraction())
    const active = visit({ contextGeneration: 3, startedAt: T0 + 60_000 })
    const snapshot = snapshotForFenceOn(db, active, T0 + 61_000)
    expect(snapshot).not.toBeNull()
    expect(snapshot?.tail[0]).toMatch(/^entry:[0-9a-f-]+ Working through the review notes\.$/)
    expect(snapshot?.validatedFacts[0]).toMatch(
      /^fact:[0-9a-f-]+ Nik asked for the demo recording before the launch video\. \[evidence: Nik: need the demo recording before launch; refs: \["visit:\d+"\]\]$/
    )
    expect(snapshot?.notifyWorthiness).toBe(0.8)
  })

  it('returns null when the persisted visit bucket no longer matches the fence', () => {
    const fence = bucketedVisit()
    db.prepare(`UPDATE context_visits SET bucketID = NULL WHERE id = ?`).run(fence.visitID)
    expect(snapshotForFenceOn(db, fence, T0 + 1_000)).toBeNull()
  })

  it('validates entry refs and fact ids with prefix normalization and bucket scoping', () => {
    const fence = bucketedVisit()
    writeCompletedExtraction(fence, extraction())
    const active = visit({ contextGeneration: 3, startedAt: T0 + 60_000 })
    const snapshot = snapshotForFenceOn(db, active, T0 + 61_000)
    const entryId = (db.prepare(`SELECT id FROM bucket_entries LIMIT 1`).get() as { id: string }).id
    const factId = (db.prepare(`SELECT id FROM bucket_facts LIMIT 1`).get() as { id: string }).id

    expect(
      validatedEntryRefsOn(
        db,
        [`entry:${entryId}`, entryId, 'entry:bogus'],
        fence.bucketID as string
      )
    ).toEqual([`entry:${entryId}`, `entry:${entryId}`])
    const ids = snapshotFactIdSet(snapshot as NonNullable<typeof snapshot>)
    expect(
      validatedFactIDsOn(
        db,
        [`fact:${factId}`, 'fact:bogus'],
        ids,
        fence.bucketID as string,
        T0 + 61_000
      )
    ).toEqual([`fact:${factId}`])
    // A fact outside the supplied snapshot never validates, even though stored.
    expect(
      validatedFactIDsOn(db, [factId], new Set<string>(), fence.bucketID as string, T0 + 61_000)
    ).toEqual([])
  })
})

describe('destination binding', () => {
  it('claims the current bucket for a new destination and repoints the binding', () => {
    const fence = bucketedVisit('Inbox — Gmail', 'Google Chrome')
    const resolved = applyDestinationOn(db, fence, 'dest:mail.google.com/inbox', T0 + 30_000)
    expect(resolved).toBe(fence.bucketID)
    const bucket = db
      .prepare(`SELECT subjectID FROM context_buckets WHERE id = ?`)
      .get(fence.bucketID) as {
      subjectID: string
    }
    expect(bucket.subjectID).toBe('dest:mail.google.com/inbox')
    const binding = db
      .prepare(`SELECT source, subjectID FROM subject_bindings WHERE bucketID = ?`)
      .get(fence.bucketID) as { source: string; subjectID: string }
    expect(binding.source).toBe('derived_destination:v1')
    expect(binding.subjectID).toBe('dest:mail.google.com/inbox')
  })

  it('merges a second title into the existing destination bucket and credits its freshness', () => {
    const first = bucketedVisit('Inbox — Gmail', 'Google Chrome')
    applyDestinationOn(db, first, 'dest:mail.google.com/inbox', T0 + 30_000)
    const before = db
      .prepare(`SELECT visitCount FROM context_buckets WHERE id = ?`)
      .get(first.bucketID) as {
      visitCount: number
    }

    const second = bucketedVisit('Starred — Gmail', 'Google Chrome')
    const resolved = applyDestinationOn(db, second, 'dest:mail.google.com/inbox', T0 + 60_000)
    expect(resolved).toBe(first.bucketID)
    const after = db
      .prepare(`SELECT visitCount, lastVisitedAt FROM context_buckets WHERE id = ?`)
      .get(first.bucketID) as {
      visitCount: number
      lastVisitedAt: number
    }
    expect(after.visitCount).toBe(before.visitCount + 1)
    expect(after.lastVisitedAt).toBe(T0 + 60_000)
    // The second title's own bucket keeps its already-written rows (no re-parenting).
    expect(second.bucketID).not.toBe(first.bucketID)
  })

  it('never overwrites explicit or previously derived bindings, and skips same-subject no-ops', () => {
    const fence = bucketedVisit('Inbox — Gmail', 'Google Chrome')
    applyDestinationOn(db, fence, 'dest:mail.google.com/inbox', T0 + 30_000)
    expect(applyDestinationOn(db, fence, 'dest:mail.google.com/starred', T0 + 31_000)).toBeNull()

    const explicitKey = referenceHashFor('google chrome::docs — google docs')
    upsertExplicitBindingOn(
      db,
      { referenceHash: explicitKey, subjectKind: 'task', subjectID: 't', workstreamID: null },
      T0
    )
    const explicitFence = visit({
      windowTitle: 'Docs — Google Docs',
      appName: 'Google Chrome',
      contextGeneration: 5
    })
    expect(
      applyDestinationOn(db, explicitFence, 'dest:docs.google.com/docs', T0 + 40_000)
    ).toBeNull()
  })
})

describe('subject bindings retention', () => {
  it('requires the sha256 prefix and bumps occurrence on conflict', () => {
    expect(
      upsertExplicitBindingOn(
        db,
        { referenceHash: 'ephemeral:x', subjectKind: 'task', subjectID: 't', workstreamID: null },
        T0
      )
    ).toBe(false)
    const hash = referenceHashFor('a::b')
    upsertExplicitBindingOn(
      db,
      { referenceHash: hash, subjectKind: 'task', subjectID: 't1', workstreamID: null },
      T0
    )
    upsertExplicitBindingOn(
      db,
      { referenceHash: hash, subjectKind: 'task', subjectID: 't2', workstreamID: 'w' },
      T0 + 1
    )
    const row = db
      .prepare(
        `SELECT subjectID, workstreamID, occurrenceCount, source FROM subject_bindings WHERE referenceHash = ?`
      )
      .get(hash) as {
      subjectID: string
      workstreamID: string
      occurrenceCount: number
      source: string
    }
    expect(row).toEqual({
      subjectID: 't2',
      workstreamID: 'w',
      occurrenceCount: 2,
      source: 'explicit_open'
    })
  })

  it('prunes unbound rows past 30 days and beyond the newest 256', () => {
    const insert = db.prepare(
      `INSERT INTO subject_bindings (referenceHash, bucketID, subjectKind, subjectID, workstreamID, confidence, source, occurrenceCount, createdAt, updatedAt)
       VALUES (?, NULL, 'task', 't', NULL, 1, 'explicit_open', 1, ?, ?)`
    )
    insert.run('sha256:old', T0 - 31 * DAY, T0 - 31 * DAY)
    for (let i = 0; i < 260; i++) insert.run(`sha256:n${i}`, T0, T0 + i)
    upsertExplicitBindingOn(
      db,
      {
        referenceHash: referenceHashFor('z::z'),
        subjectKind: 'task',
        subjectID: 't',
        workstreamID: null
      },
      T0 + 10_000
    )
    const count = (
      db.prepare(`SELECT COUNT(*) AS n FROM subject_bindings WHERE bucketID IS NULL`).get() as {
        n: number
      }
    ).n
    expect(count).toBe(256)
    expect(
      db.prepare(`SELECT 1 AS ok FROM subject_bindings WHERE referenceHash = 'sha256:old'`).get()
    ).toBeUndefined()
  })

  it('lookup honors the 30-day freshness window', () => {
    const hash = referenceHashFor('a::b')
    upsertExplicitBindingOn(
      db,
      { referenceHash: hash, subjectKind: 'task', subjectID: 't', workstreamID: null },
      T0
    )
    expect(lookupBindingOn(db, hash, T0 + 29 * DAY)).not.toBeNull()
    expect(lookupBindingOn(db, hash, T0 + 31 * DAY)).toBeNull()
  })
})

describe('deterministic GC', () => {
  it('drops stale buckets while protecting those with an active visit', () => {
    const stale = bucketedVisit('Old work', 'Code')
    finalizeVisitOn(db, stale, {
      outcome: 'completed',
      exitReason: 'context_switch',
      endedAt: T0 + 5_000,
      lastFrameId: null
    })
    const activeFence = bucketedVisit('Live work', 'Code')
    db.prepare(`UPDATE context_buckets SET lastVisitedAt = ? WHERE id IN (?, ?)`).run(
      T0 - 31 * DAY,
      stale.bucketID,
      activeFence.bucketID
    )

    runDeterministicGCOn(db, T0)
    expect(
      db.prepare(`SELECT 1 AS ok FROM context_buckets WHERE id = ?`).get(stale.bucketID)
    ).toBeUndefined()
    expect(
      db.prepare(`SELECT 1 AS ok FROM context_buckets WHERE id = ?`).get(activeFence.bucketID)
    ).toBeTruthy()
    // The stale bucket's visit rows survive with a nulled reference.
    const visitRow = db
      .prepare(`SELECT bucketID FROM context_visits WHERE id = ?`)
      .get(stale.visitID) as {
      bucketID: string | null
    }
    expect(visitRow.bucketID).toBeNull()
  })

  it('keeps only the newest 250 idle buckets', () => {
    const insert = db.prepare(
      `INSERT INTO context_buckets (id, subjectKind, subjectID, workstreamID, createdAt, updatedAt, lastVisitedAt)
       VALUES (?, 'context', ?, NULL, ?, ?, ?)`
    )
    for (let i = 0; i < 260; i++) {
      const at = T0 - i * 1_000
      insert.run(`b${i}`, `s${i}`, at, at, at)
    }
    runDeterministicGCOn(db, T0)
    const count = (db.prepare(`SELECT COUNT(*) AS n FROM context_buckets`).get() as { n: number }).n
    expect(count).toBe(250)
    expect(db.prepare(`SELECT 1 AS ok FROM context_buckets WHERE id = 'b0'`).get()).toBeTruthy()
    expect(
      db.prepare(`SELECT 1 AS ok FROM context_buckets WHERE id = 'b259'`).get()
    ).toBeUndefined()
  })

  it('deletes expired facts, non-armed candidates, and expired deliveries', () => {
    const fence = bucketedVisit()
    db.prepare(
      `INSERT INTO bucket_entries (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey, narrative, evidenceRefsJson, tokenCount, createdAt)
       VALUES ('e1', ?, ?, 'Code', 'raw', 'norm', 'n', '[]', 1, ?)`
    ).run(fence.bucketID, fence.visitID, T0)
    db.prepare(
      `INSERT INTO bucket_facts (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText, evidenceRefsJson, validityState, confidence, notifyWorthiness, expiresAt, createdAt, updatedAt)
       VALUES ('f1', ?, 'e1', 'Code', 's', '[]', 'e', '[]', 'validated', 1, 1, ?, ?, ?)`
    ).run(fence.bucketID, T0 - 1, T0 - DAY, T0 - DAY)
    db.prepare(
      `INSERT INTO proactive_candidates (id, bucketID, message, groundingFactIDsJson, triggerNote, state, createdAt, expiresAt)
       VALUES ('c1', ?, 'm', '[]', 't', 'consumed', ?, ?)`
    ).run(fence.bucketID, T0, T0 + DAY)
    db.prepare(
      `INSERT INTO proactive_deliveries (id, decisionType, lifecycleState, provenanceJson, attemptedAt, expiresAt, createdAt)
       VALUES ('d1', 'silence', 'failed', '{}', ?, ?, ?)`
    ).run(T0 - DAY, T0 - 1, T0 - DAY)

    runDeterministicGCOn(db, T0)
    expect(db.prepare(`SELECT 1 AS ok FROM bucket_facts WHERE id = 'f1'`).get()).toBeUndefined()
    expect(
      db.prepare(`SELECT 1 AS ok FROM proactive_candidates WHERE id = 'c1'`).get()
    ).toBeUndefined()
    expect(
      db.prepare(`SELECT 1 AS ok FROM proactive_deliveries WHERE id = 'd1'`).get()
    ).toBeUndefined()
  })
})
