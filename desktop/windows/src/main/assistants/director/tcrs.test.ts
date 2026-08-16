import { describe, it, expect, beforeEach } from 'vitest'
import {
  normalizedEvent,
  appWindowEvent,
  TaskContextEventAccumulator,
  contextMatches,
  materialHint,
  TaskContextualResurfacingService,
  evaluateInterruptionGate,
  INTERRUPTION_SAFE_DEFAULT,
  sha256Hex,
  type TaskLocalContextEvent,
  type TcrsDeps,
  type InterruptionEnvironment,
  type InterruptionCandidate
} from './tcrs'

const T0 = 1_760_000_000_000

const event = (over: Partial<TaskLocalContextEvent> = {}): TaskLocalContextEvent => ({
  kind: 'app_window',
  referenceHash: 'sha256:' + 'a'.repeat(64),
  subject: { kind: 'task', id: 't-1', workstreamID: null },
  urgency: 'can_wait',
  occurredAt: T0,
  expiresAt: T0 + 300_000,
  ...over
})

describe('event construction', () => {
  it('normalizes, lowercases, and hashes the raw reference', () => {
    const e = normalizedEvent({
      kind: 'meeting',
      rawReference: '  Meeting-Active ',
      occurredAt: T0
    })
    expect(e?.referenceHash).toBe('sha256:' + sha256Hex('meeting-active'))
    expect(e?.expiresAt).toBe(T0 + 300_000)
    expect(e?.urgency).toBe('can_wait')
  })

  it('rejects empty references and non-positive lifetimes', () => {
    expect(normalizedEvent({ kind: 'meeting', rawReference: '   ', occurredAt: T0 })).toBeNull()
    expect(
      normalizedEvent({ kind: 'meeting', rawReference: 'x', occurredAt: T0, lifetimeMs: 0 })
    ).toBeNull()
  })

  it('app_window hashes appName newline normalizedTitle, with untitled fallback', () => {
    const titled = appWindowEvent({ appName: 'Code', windowTitle: 'main.ts', occurredAt: T0 })
    expect(titled?.referenceHash).toBe('sha256:' + sha256Hex('code\nmain.ts'))
    const blank = appWindowEvent({ appName: 'Code', windowTitle: '  ', occurredAt: T0 })
    expect(blank?.referenceHash).toBe('sha256:' + sha256Hex('code\nuntitled'))
  })
})

describe('accumulator', () => {
  it('replaces in place on (kind, hash, subject) match and caps at 16 per key', () => {
    const acc = new TaskContextEventAccumulator()
    acc.insert(event({ occurredAt: T0, expiresAt: T0 + 1_000 }), T0)
    acc.insert(event({ occurredAt: T0 + 500, expiresAt: T0 + 10_000 }), T0 + 500)
    const drained = acc.drain(T0 + 600)
    expect(drained.length).toBe(1)
    expect(drained[0].expiresAt).toBe(T0 + 10_000)

    for (let i = 0; i < 20; i++) {
      acc.insert(event({ referenceHash: `sha256:${String(i).padStart(64, '0')}` }), T0)
    }
    expect(acc.drain(T0).length).toBe(16)
  })

  it('drops expired events on insert and drain', () => {
    const acc = new TaskContextEventAccumulator()
    acc.insert(event({ expiresAt: T0 - 1 }), T0)
    acc.insert(event({ referenceHash: 'sha256:' + 'b'.repeat(64), expiresAt: T0 + 100 }), T0)
    expect(acc.drain(T0 + 200)).toEqual([])
  })
})

describe('contextMatches and materialHint', () => {
  it('groups by subject with deduped sorted signals, sorted matches, subject-less dropped', () => {
    const matches = contextMatches([
      event({ kind: 'app_window' }),
      event({ kind: 'meeting' }),
      event({ kind: 'app_window' }),
      event({ subject: null }),
      event({ kind: 'person', subject: { kind: 'candidate', id: 'c-1', workstreamID: 'w' } })
    ])
    expect(matches).toEqual([
      { subject_kind: 'candidate', subject_id: 'c-1', signals: ['person'] },
      { subject_kind: 'task', subject_id: 't-1', signals: ['app', 'meeting'] }
    ])
  })

  it('material hint is ctx: + 32 hex and flips with the urgency suffix', () => {
    const matches = contextMatches([event()])
    const calm = materialHint(matches, false)
    const urgent = materialHint(matches, true)
    expect(calm).toMatch(/^ctx:[0-9a-f]{32}$/)
    expect(urgent).not.toBe(calm)
  })
})

describe('flush pipeline', () => {
  let deps: TcrsDeps
  let nowMs: number
  let epoch: number
  let owner: string | null
  let bucketsOn: boolean
  let control: { workflowMode: string; accountGeneration: number | null }
  let calls: string[]
  let published: unknown[]
  let snapshots: Array<{ snapshot_id: string; matches: unknown[] }>
  let pendingDebounce: (() => void) | null

  function makeService(): TaskContextualResurfacingService {
    deps = {
      bucketsEnabled: () => bucketsOn,
      ownerId: () => owner,
      sessionEpoch: () => epoch,
      deviceId: () => 'windows_abcd1234',
      client: {
        getControl: async () => {
          calls.push('control')
          return control
        },
        putContextSnapshot: async (snapshot, headers) => {
          calls.push(
            `put:${headers.idempotencyKey === snapshot.snapshot_id}:${headers.accountGeneration}`
          )
          snapshots.push({ snapshot_id: snapshot.snapshot_id, matches: snapshot.matches })
        },
        evaluate: async (body) => {
          calls.push(`evaluate:${body.material_hint.startsWith('ctx:')}`)
          return { schema_version: 1, recommendations: [] }
        }
      },
      publishProjection: (raw) => {
        published.push(raw)
      },
      now: () => nowMs,
      setDebounce: (fn) => {
        pendingDebounce = fn
        return 1
      },
      clearDebounce: () => {
        pendingDebounce = null
      }
    }
    return new TaskContextualResurfacingService(deps)
  }

  beforeEach(() => {
    nowMs = T0
    epoch = 1
    owner = 'uid-1'
    bucketsOn = false
    control = { workflowMode: 'read', accountGeneration: 3 }
    calls = []
    published = []
    snapshots = []
    pendingDebounce = null
  })

  it('debounces, gates on control, PUTs with idempotency headers, evaluates, publishes', async () => {
    const service = makeService()
    service.observe(event())
    expect(pendingDebounce).not.toBeNull()
    await service.flush()
    expect(calls).toEqual(['control', 'put:true:3', 'evaluate:true'])
    expect(published.length).toBe(1)
    expect(snapshots[0].snapshot_id).toMatch(/^ctx-[0-9a-f-]{36}$/)
  })

  it('skips the network entirely when the material hint repeats within 5 minutes', async () => {
    const service = makeService()
    service.observe(event())
    await service.flush()
    calls = []
    service.observe(event({ occurredAt: nowMs, expiresAt: nowMs + 300_000 }))
    nowMs += 60_000
    await service.flush()
    expect(calls).toEqual([])

    // After the window the same hint re-evaluates.
    nowMs += 301_000
    service.observe(event({ occurredAt: nowMs, expiresAt: nowMs + 300_000 }))
    await service.flush()
    expect(calls[0]).toBe('control')
  })

  it('a non-read workflow mode is a silent no-op that keeps the dedupe memory unset', async () => {
    control = { workflowMode: 'off', accountGeneration: 0 }
    const service = makeService()
    service.observe(event())
    await service.flush()
    expect(calls).toEqual(['control'])
    expect(published).toEqual([])

    // The next flush retries: the memory never advanced.
    control = { workflowMode: 'read', accountGeneration: 3 }
    service.observe(event({ occurredAt: nowMs + 1, expiresAt: nowMs + 300_000 }))
    await service.flush()
    expect(calls).toContain('evaluate:true')
  })

  it('abandons silently when the owner changes mid-flight', async () => {
    const service = makeService()
    service.observe(event())
    deps.client.getControl = async () => {
      owner = 'uid-2'
      return control
    }
    await service.flush()
    expect(published).toEqual([])
  })

  it('resets and drops events when the buckets engine owns the world', () => {
    bucketsOn = true
    const service = makeService()
    service.observe(event())
    expect(service.pendingKeyCount()).toBe(0)
  })

  it('client errors log once and never poison the next cycle', async () => {
    const service = makeService()
    const logs: string[] = []
    deps.log = (m) => logs.push(m)
    deps.client.getControl = async () => {
      throw new Error('down')
    }
    service.observe(event())
    await service.flush()
    expect(logs.length).toBe(1)

    deps.client.getControl = async () => control
    service.observe(event({ occurredAt: nowMs + 1, expiresAt: nowMs + 300_000 }))
    await service.flush()
    expect(published.length).toBe(1)
  })
})

describe('interruption gate', () => {
  const candidate = (over: Partial<InterruptionCandidate> = {}): InterruptionCandidate => ({
    recommendationID: 'ov:dk',
    interventionID: 'iv-1',
    dedupeKey: 'dk',
    headline: 'h',
    whyNow: 'w',
    recommendedAction: 'a',
    expiresAt: T0 + 60_000,
    canWait: false,
    ...over
  })

  const env = (over: Partial<InterruptionEnvironment> = {}): InterruptionEnvironment => ({
    cohort: 'dogfood',
    masterNotificationsEnabled: true,
    frequencyEnabled: true,
    ambientFrequencyEligible: true,
    taskNotificationsEnabled: true,
    focusSuppressed: false,
    now: T0,
    sameDay: (a, b) => Math.floor(a / 86_400_000) === Math.floor(b / 86_400_000),
    ...over
  })

  const optedIn = { ...INTERRUPTION_SAFE_DEFAULT, userOptedIn: true }
  const emptyLedger = { sentAt: [], dedupeExpirations: {} }

  it('the safe default is not enrolled; opt-in enables dogfood only', () => {
    expect(
      evaluateInterruptionGate(candidate(), INTERRUPTION_SAFE_DEFAULT, env(), emptyLedger).reason
    ).toBe('not_enrolled')
    expect(
      evaluateInterruptionGate(candidate(), optedIn, env({ cohort: 'beta' }), emptyLedger).reason
    ).toBe('not_enrolled')
    expect(evaluateInterruptionGate(candidate(), optedIn, env(), emptyLedger).reason).toBe(
      'allowed'
    )
  })

  it('applies reasons in the exact order and records the send on allowed', () => {
    expect(
      evaluateInterruptionGate(
        candidate(),
        optedIn,
        env({ masterNotificationsEnabled: false }),
        emptyLedger
      ).reason
    ).toBe('master_disabled')
    expect(
      evaluateInterruptionGate(
        candidate(),
        optedIn,
        env({ taskNotificationsEnabled: false }),
        emptyLedger
      ).reason
    ).toBe('task_disabled')
    expect(
      evaluateInterruptionGate(candidate({ expiresAt: T0 - 1 }), optedIn, env(), emptyLedger).reason
    ).toBe('expired')
    expect(
      evaluateInterruptionGate(candidate({ canWait: true }), optedIn, env(), emptyLedger).reason
    ).toBe('can_wait')

    const allowed = evaluateInterruptionGate(candidate(), optedIn, env(), emptyLedger)
    expect(allowed.ledger.sentAt).toEqual([T0])
    expect(allowed.ledger.dedupeExpirations).toEqual({ dk: T0 + 60_000 })

    // Same dedupe key while unexpired: duplicate.
    expect(
      evaluateInterruptionGate(candidate(), optedIn, env({ now: T0 + 1_000 }), allowed.ledger)
        .reason
    ).toBe('duplicate')
  })

  it('enforces the daily budget and minimum spacing', () => {
    const twoToday = { sentAt: [T0 - 1_000, T0 - 2_000], dedupeExpirations: {} }
    expect(
      evaluateInterruptionGate(candidate({ dedupeKey: 'other' }), optedIn, env(), twoToday).reason
    ).toBe('daily_budget')
    const oneRecent = { sentAt: [T0 - 60_000], dedupeExpirations: {} }
    expect(
      evaluateInterruptionGate(candidate({ dedupeKey: 'other' }), optedIn, env(), oneRecent).reason
    ).toBe('minimum_spacing')
  })
})
