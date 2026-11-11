import { describe, it, expect } from 'vitest'
import {
  mapWireStatusToDisplay,
  normalizeWireStatus,
  isFinished,
  isTerminalWire,
  displayLabel,
  displayTintToken,
  deriveTitle,
  mergeProjectedPills,
  markViewed,
  expireViewedFinished,
  trimForSoftCap,
  SOFT_CAP,
  VIEWED_FINISHED_TTL_MS,
  type AgentPill,
  type AgentPillWireStatus,
  type AgentPillDisplayStatus,
  type PillProjectionRow
} from './agentPills'

const row = (partial: Partial<PillProjectionRow> = {}): PillProjectionRow => ({
  id: 'p1',
  runId: 'r1',
  sessionId: 's1',
  title: 'Fix the bug',
  status: 'running',
  latestActivity: 'Working…',
  query: 'please fix the login bug',
  createdAtMs: 1000,
  completedAtMs: null,
  provider: null,
  errorCode: null,
  errorMessage: null,
  ...partial
})

const pill = (partial: Partial<AgentPill> = {}): AgentPill => ({
  id: 'p1',
  runId: 'r1',
  sessionId: 's1',
  title: 'Fix the bug',
  displayStatus: 'running',
  latestActivity: '',
  query: '',
  createdAtMs: 1000,
  completedAtMs: null,
  errorMessage: null,
  provider: null,
  viewedAtMs: null,
  ...partial
})

describe('mapWireStatusToDisplay (spec §b, the full status mapping)', () => {
  const cases: Array<[AgentPillWireStatus, AgentPillDisplayStatus]> = [
    ['idle', 'queued'],
    ['queued', 'queued'],
    ['starting', 'starting'],
    ['running', 'running'],
    ['waiting_input', 'running'],
    ['waiting_approval', 'running'],
    ['cancelling', 'running'],
    ['succeeded', 'done'],
    ['completed', 'done'],
    ['cancelled', 'stopped'],
    ['failed', 'failed'],
    ['timed_out', 'failed'],
    ['orphaned', 'failed']
  ]
  it.each(cases)('%s → %s', (wire, display) => {
    expect(mapWireStatusToDisplay(wire)).toBe(display)
  })
})

describe('normalizeWireStatus', () => {
  it('passes through a known wire status', () => {
    expect(normalizeWireStatus('running')).toBe('running')
    expect(normalizeWireStatus('timed_out')).toBe('timed_out')
  })
  it("coerces an unknown status to non-terminal 'idle' (never spuriously finished)", () => {
    expect(normalizeWireStatus('unknown')).toBe('idle')
    expect(normalizeWireStatus('')).toBe('idle')
    expect(isFinished(mapWireStatusToDisplay(normalizeWireStatus('garbage')))).toBe(false)
  })
})

describe('isFinished / isTerminalWire', () => {
  it('isFinished is true only for done/stopped/failed', () => {
    expect(isFinished('done')).toBe(true)
    expect(isFinished('stopped')).toBe(true)
    expect(isFinished('failed')).toBe(true)
    expect(isFinished('running')).toBe(false)
    expect(isFinished('queued')).toBe(false)
    expect(isFinished('starting')).toBe(false)
  })
  it('isTerminalWire covers the terminal wire set but not cancelling/waiting', () => {
    for (const w of [
      'succeeded',
      'completed',
      'cancelled',
      'failed',
      'timed_out',
      'orphaned'
    ] as const) {
      expect(isTerminalWire(w)).toBe(true)
    }
    for (const w of [
      'idle',
      'queued',
      'starting',
      'running',
      'waiting_input',
      'waiting_approval',
      'cancelling'
    ] as const) {
      expect(isTerminalWire(w)).toBe(false)
    }
  })
})

describe('displayLabel / displayTintToken', () => {
  it('labels each display status', () => {
    expect(displayLabel('queued')).toBe('Queued')
    expect(displayLabel('starting')).toBe('Starting')
    expect(displayLabel('running')).toBe('Running')
    expect(displayLabel('done')).toBe('Done')
    expect(displayLabel('stopped')).toBe('Stopped')
    expect(displayLabel('failed')).toBe('Failed')
  })
  it('maps tints to neutral tokens (never a raw color, never purple)', () => {
    expect(displayTintToken('running')).toBe('running')
    expect(displayTintToken('done')).toBe('done')
    expect(displayTintToken('stopped')).toBe('stopped')
    expect(displayTintToken('failed')).toBe('failed')
    // queued + starting both collapse to the neutral token.
    expect(displayTintToken('queued')).toBe('queued')
    expect(displayTintToken('starting')).toBe('queued')
  })
  it('emits no hex / purple in any token', () => {
    const statuses: AgentPillDisplayStatus[] = [
      'queued',
      'starting',
      'running',
      'done',
      'stopped',
      'failed'
    ]
    for (const s of statuses) {
      const token = displayTintToken(s)
      expect(token).not.toMatch(/#|purple|violet|indigo/i)
    }
  })
})

describe('deriveTitle (cap 32, query fallback)', () => {
  it('uses a non-empty kernel title', () => {
    expect(deriveTitle({ title: 'Rename the widget', query: 'ignored' })).toBe('Rename the widget')
  })
  it('caps the title at 32 chars', () => {
    const long = 'x'.repeat(50)
    expect(deriveTitle({ title: long, query: '' })).toBe('x'.repeat(32))
    expect(deriveTitle({ title: long, query: '' }).length).toBe(32)
  })
  it('derives the first ~3 words from query when title is empty', () => {
    expect(deriveTitle({ title: '', query: 'please fix the login bug now' })).toBe('please fix the')
    expect(deriveTitle({ title: '   ', query: 'refactor auth module carefully' })).toBe(
      'refactor auth module'
    )
  })
  it("falls back to 'Agent' when both title and query are empty", () => {
    expect(deriveTitle({ title: '', query: '' })).toBe('Agent')
    expect(deriveTitle({ title: null, query: '' })).toBe('Agent')
  })
})

describe('mergeProjectedPills — create / update by id', () => {
  it('creates a new pill for an unseen id', () => {
    const { pills, droppedMissingId } = mergeProjectedPills([], [row()], 5000)
    expect(droppedMissingId).toBe(0)
    expect(pills).toHaveLength(1)
    expect(pills[0]).toMatchObject({
      id: 'p1',
      runId: 'r1',
      sessionId: 's1',
      title: 'Fix the bug',
      displayStatus: 'running',
      viewedAtMs: null
    })
  })

  it('updates an existing pill in place by id, preserving array position', () => {
    const existing = [pill({ id: 'a' }), pill({ id: 'b', displayStatus: 'queued' })]
    const { pills } = mergeProjectedPills(
      existing,
      [
        row({
          id: 'b',
          runId: 'rb',
          sessionId: 'sb',
          status: 'running',
          latestActivity: 'Now working'
        })
      ],
      5000
    )
    expect(pills).toHaveLength(2)
    expect(pills[1].id).toBe('b')
    expect(pills[1].displayStatus).toBe('running')
    expect(pills[1].latestActivity).toBe('Now working')
  })

  it('keeps existing pills that are absent from the new rows', () => {
    const existing = [pill({ id: 'a', displayStatus: 'done', completedAtMs: 10 })]
    const { pills } = mergeProjectedPills(existing, [], 5000)
    expect(pills).toHaveLength(1)
    expect(pills[0].id).toBe('a')
  })
})

describe('mergeProjectedPills — drop-missing-id counting', () => {
  it('drops and counts a row missing sessionId', () => {
    const { pills, droppedMissingId } = mergeProjectedPills([], [row({ sessionId: null })], 5000)
    expect(pills).toHaveLength(0)
    expect(droppedMissingId).toBe(1)
  })
  it('drops and counts a row missing runId', () => {
    const { pills, droppedMissingId } = mergeProjectedPills([], [row({ runId: null })], 5000)
    expect(pills).toHaveLength(0)
    expect(droppedMissingId).toBe(1)
  })
  it('drops and counts a row missing id', () => {
    const { droppedMissingId } = mergeProjectedPills([], [row({ id: null })], 5000)
    expect(droppedMissingId).toBe(1)
  })
  it('treats a whitespace-only id/runId/sessionId as missing', () => {
    const { droppedMissingId } = mergeProjectedPills([], [row({ runId: '   ' })], 5000)
    expect(droppedMissingId).toBe(1)
  })
  it('counts every dropped row and still merges the valid ones', () => {
    const rows = [
      row({ id: 'ok', runId: 'r', sessionId: 's' }),
      row({ sessionId: null }),
      row({ runId: null })
    ]
    const { pills, droppedMissingId } = mergeProjectedPills([], rows, 5000)
    expect(pills).toHaveLength(1)
    expect(pills[0].id).toBe('ok')
    expect(droppedMissingId).toBe(2)
  })
})

describe('mergeProjectedPills — no resurrection of a finished pill', () => {
  it('ignores a later non-terminal row once the pill is finished', () => {
    const existing = [
      pill({ displayStatus: 'done', completedAtMs: 4000, latestActivity: 'All done' })
    ]
    const { pills } = mergeProjectedPills(
      existing,
      [row({ status: 'running', latestActivity: 'Working…' })],
      9000
    )
    expect(pills[0].displayStatus).toBe('done')
    expect(pills[0].completedAtMs).toBe(4000)
    expect(pills[0].latestActivity).toBe('All done') // stale row ignored wholesale
  })
  it('a stopped pill is not revived by a running poll', () => {
    const existing = [pill({ displayStatus: 'stopped', completedAtMs: 4000 })]
    const { pills } = mergeProjectedPills(existing, [row({ status: 'waiting_approval' })], 9000)
    expect(pills[0].displayStatus).toBe('stopped')
  })
  it('still allows a finished pill to update to another terminal status', () => {
    const existing = [pill({ displayStatus: 'done', completedAtMs: 4000 })]
    const { pills } = mergeProjectedPills(
      existing,
      [row({ status: 'failed', errorMessage: 'blew up' })],
      9000
    )
    expect(pills[0].displayStatus).toBe('failed')
    expect(pills[0].errorMessage).toBe('blew up')
  })
})

describe('mergeProjectedPills — completedAtMs on transition', () => {
  it('sets completedAtMs from the row when transitioning to finished', () => {
    const existing = [pill({ displayStatus: 'running', completedAtMs: null })]
    const { pills } = mergeProjectedPills(
      existing,
      [row({ status: 'succeeded', completedAtMs: 7777 })],
      9000
    )
    expect(pills[0].displayStatus).toBe('done')
    expect(pills[0].completedAtMs).toBe(7777)
  })
  it('falls back to nowMs when the row omits completedAtMs', () => {
    const existing = [pill({ displayStatus: 'running', completedAtMs: null })]
    const { pills } = mergeProjectedPills(
      existing,
      [row({ status: 'succeeded', completedAtMs: null })],
      9000
    )
    expect(pills[0].completedAtMs).toBe(9000)
  })
  it('leaves completedAtMs null while still running', () => {
    const { pills } = mergeProjectedPills([], [row({ status: 'running' })], 9000)
    expect(pills[0].completedAtMs).toBeNull()
  })
})

describe('mergeProjectedPills — failed carries an error, preserves local state', () => {
  it("a failed pill without a row error still carries the generic 'Agent failed'", () => {
    const { pills } = mergeProjectedPills([], [row({ status: 'failed', errorMessage: null })], 9000)
    expect(pills[0].displayStatus).toBe('failed')
    expect(pills[0].errorMessage).toBe('Agent failed')
  })
  it('a failed pill uses the row error when present', () => {
    const { pills } = mergeProjectedPills(
      [],
      [row({ status: 'timed_out', errorMessage: 'timed out after 5m' })],
      9000
    )
    expect(pills[0].errorMessage).toBe('timed out after 5m')
  })
  it('preserves viewedAtMs across a merge', () => {
    const existing = [pill({ displayStatus: 'done', viewedAtMs: 1234, completedAtMs: 100 })]
    const { pills } = mergeProjectedPills(existing, [row({ status: 'succeeded' })], 9000)
    expect(pills[0].viewedAtMs).toBe(1234)
  })
  it('preserves provider when a later row omits it', () => {
    const existing = [pill({ provider: 'gemini' })]
    const { pills } = mergeProjectedPills(
      existing,
      [row({ provider: null, status: 'running' })],
      9000
    )
    expect(pills[0].provider).toBe('gemini')
  })
})

describe('markViewed', () => {
  it('stamps viewedAtMs on a finished pill', () => {
    const pills = [pill({ displayStatus: 'done' })]
    const out = markViewed(pills, 'p1', 5555)
    expect(out[0].viewedAtMs).toBe(5555)
  })
  it('is a no-op on a non-finished pill', () => {
    const pills = [pill({ displayStatus: 'running' })]
    const out = markViewed(pills, 'p1', 5555)
    expect(out[0].viewedAtMs).toBeNull()
  })
  it('is a no-op for an unknown id', () => {
    const pills = [pill({ id: 'p1', displayStatus: 'done' })]
    const out = markViewed(pills, 'nope', 5555)
    expect(out[0].viewedAtMs).toBeNull()
  })
})

describe('expireViewedFinished', () => {
  const ttl = VIEWED_FINISHED_TTL_MS
  it('removes a viewed finished pill past its TTL', () => {
    const pills = [pill({ id: 'old', displayStatus: 'done', viewedAtMs: 0 })]
    expect(expireViewedFinished(pills, ttl + 1)).toHaveLength(0)
  })
  it('keeps a viewed finished pill still within its TTL', () => {
    const pills = [pill({ id: 'recent', displayStatus: 'done', viewedAtMs: 0 })]
    expect(expireViewedFinished(pills, ttl - 1)).toHaveLength(1)
  })
  it('never expires an unviewed finished pill', () => {
    const pills = [pill({ id: 'unviewed', displayStatus: 'failed', viewedAtMs: null })]
    expect(expireViewedFinished(pills, Number.MAX_SAFE_INTEGER)).toHaveLength(1)
  })
  it('never expires a non-finished pill', () => {
    const pills = [pill({ id: 'running', displayStatus: 'running', viewedAtMs: 0 })]
    expect(expireViewedFinished(pills, Number.MAX_SAFE_INTEGER)).toHaveLength(1)
  })
  it('never expires the active pill even when its viewed TTL has elapsed', () => {
    const pills = [pill({ id: 'active', displayStatus: 'done', viewedAtMs: 0 })]
    expect(expireViewedFinished(pills, ttl + 10000, ttl, 'active')).toHaveLength(1)
  })
  it('uses the default TTL when none is passed', () => {
    const pills = [pill({ id: 'x', displayStatus: 'done', viewedAtMs: 0 })]
    expect(expireViewedFinished(pills, VIEWED_FINISHED_TTL_MS + 1)).toHaveLength(0)
  })
})

describe('trimForSoftCap', () => {
  it('is a no-op at or under the cap', () => {
    const pills = Array.from({ length: SOFT_CAP }, (_, i) =>
      pill({ id: `p${i}`, displayStatus: 'done', createdAtMs: i })
    )
    expect(trimForSoftCap(pills, null)).toHaveLength(SOFT_CAP)
  })

  it('evicts the oldest done pill first when over cap', () => {
    // 9 done pills, ages 0..8 → oldest (age 0) is evicted, one over the cap.
    const pills = Array.from({ length: SOFT_CAP + 1 }, (_, i) =>
      pill({ id: `p${i}`, displayStatus: 'done', createdAtMs: i })
    )
    const out = trimForSoftCap(pills, null)
    expect(out).toHaveLength(SOFT_CAP)
    expect(out.find((p) => p.id === 'p0')).toBeUndefined() // oldest done gone
    expect(out.find((p) => p.id === 'p8')).toBeDefined()
  })

  it('never evicts the active pill even if it is the oldest done', () => {
    const pills = Array.from({ length: SOFT_CAP + 1 }, (_, i) =>
      pill({ id: `p${i}`, displayStatus: 'done', createdAtMs: i })
    )
    const out = trimForSoftCap(pills, 'p0') // p0 is oldest but active
    expect(out.find((p) => p.id === 'p0')).toBeDefined()
    expect(out.find((p) => p.id === 'p1')).toBeUndefined() // next-oldest done evicted instead
  })

  it('never evicts a non-finished pill (cap stays soft)', () => {
    const pills = Array.from({ length: SOFT_CAP + 2 }, (_, i) =>
      pill({ id: `p${i}`, displayStatus: 'running', createdAtMs: i })
    )
    const out = trimForSoftCap(pills, null)
    expect(out).toHaveLength(SOFT_CAP + 2) // nothing finished → nothing evicted
  })

  it('evicts oldest done before any other finished kind, then oldest finished', () => {
    // Ages: a stopped/oldest (0), a done (1), a failed (2), then 8 running.
    const pills = [
      pill({ id: 'stopped-old', displayStatus: 'stopped', createdAtMs: 0 }),
      pill({ id: 'done-1', displayStatus: 'done', createdAtMs: 1 }),
      pill({ id: 'failed-2', displayStatus: 'failed', createdAtMs: 2 }),
      ...Array.from({ length: 8 }, (_, i) =>
        pill({ id: `run${i}`, displayStatus: 'running', createdAtMs: 10 + i })
      )
    ]
    // 11 pills, cap 8 → evict 3. Order: done-1 (only done) first, then oldest
    // finished remaining = stopped-old, then failed-2. All running survive.
    const out = trimForSoftCap(pills, null)
    expect(out).toHaveLength(SOFT_CAP)
    expect(out.find((p) => p.id === 'done-1')).toBeUndefined()
    expect(out.find((p) => p.id === 'stopped-old')).toBeUndefined()
    expect(out.find((p) => p.id === 'failed-2')).toBeUndefined()
    expect(out.filter((p) => p.displayStatus === 'running')).toHaveLength(8)
  })

  it('preserves relative order of survivors', () => {
    const pills = [
      pill({ id: 'a', displayStatus: 'running', createdAtMs: 0 }),
      pill({ id: 'b', displayStatus: 'done', createdAtMs: 1 }),
      ...Array.from({ length: 7 }, (_, i) =>
        pill({ id: `c${i}`, displayStatus: 'running', createdAtMs: 10 + i })
      )
    ]
    const out = trimForSoftCap(pills, null) // 9 pills → evict the one done (b)
    expect(out.map((p) => p.id)).toEqual(['a', 'c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6'])
  })
})
