// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  CHOOSE_REPLACEMENT,
  TARGET_UNAVAILABLE,
  DashboardIntelligenceStore,
  FEEDBACK_SAVED_ERROR,
  RETRY_BANNER,
  currentGoals,
  endedGoals,
  focusedGoals,
  projectRecommendations
} from './dashboardStore'
import { enqueueFeedback, loadOutbox } from './feedbackOutbox'
import { readWmnProjection, type WmnProjection } from './wireTypes'

vi.mock('../persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../apiClient', () => ({ omiApi: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
const trackEvent = vi.hoisted(() => vi.fn())
vi.mock('../analytics', () => ({ trackEvent }))

const NOW = Date.parse('2026-08-16T12:00:00Z')
const FUTURE = '2026-08-16T18:00:00Z'
const PAST = '2026-08-16T06:00:00Z'

const wireRow = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  intervention_id: 'iv-1',
  output_version: 'out-1',
  subject_kind: 'task',
  subject_id: 'task-1',
  feedback_subject_kind: 'task',
  feedback_subject_id: 'task-1',
  destination_task_id: null,
  destination_workstream_id: null,
  headline: 'Finish the report',
  why_now: 'Due soon',
  goal_or_workstream_label: null,
  recommended_action: 'Open it',
  alternative_action: null,
  evidence_preview: 'seen in Slack',
  evidence_refs: [{ kind: 'external', id: 'e1', scope: 'canonical' }],
  dedupe_key: 'dk-1',
  expires_at: FUTURE,
  ...over
})

const wireProjection = (rows: Record<string, unknown>[], over: Record<string, unknown> = {}) =>
  readWmnProjection({
    schema_version: 1,
    evaluation_id: 'ev-1',
    output_version: 'out-1',
    material_version: 'mat-1',
    generated_at: PAST,
    expires_at: FUTURE,
    recommendations: rows,
    ...over
  }) as WmnProjection

const wireGoal = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  goal_id: 'g-1',
  id: 'g-1',
  title: 'Ship the launch',
  desired_outcome: 'Launched',
  status: 'focused',
  focus_rank: 0,
  is_active: true,
  updated_at: '2026-08-10T00:00:00Z',
  current_value: 1,
  target_value: 3,
  ...over
})

type Routes = Record<string, unknown | (() => unknown)>

function makeStore(routes: Routes, capture?: { posts: unknown[][]; deletes: unknown[][] }) {
  const resolve = (path: string): unknown => {
    const hit = routes[path]
    if (hit === undefined) {
      const err = new Error('not found') as Error & { response?: { status: number } }
      err.response = { status: 404 }
      throw err
    }
    const value = typeof hit === 'function' ? (hit as () => unknown)() : hit
    if (value instanceof Error) throw value
    return value
  }
  const store = new DashboardIntelligenceStore({
    get: vi.fn(async (path: string) => ({ data: resolve(path) })) as never,
    post: vi.fn(async (path: string, body: unknown, config: unknown) => {
      capture?.posts.push([path, body, config])
      return { data: resolve(`POST ${path}`) }
    }) as never,
    del: vi.fn(async (path: string, config: unknown) => {
      capture?.deletes.push([path, config])
      return { data: resolve(`DELETE ${path}`) }
    }) as never,
    now: () => NOW,
    uuid: () => 'UUID-FIXED',
    ownerId: () => 'uid-1'
  })
  return store
}

const READ_CONTROL = { workflow_mode: 'read', account_generation: 3 }

beforeEach(() => {
  window.localStorage.clear()
  trackEvent.mockClear()
})

describe('projection rules', () => {
  it('an expired projection yields nothing even with live rows', () => {
    const projection = wireProjection([wireRow()], { expires_at: PAST })
    expect(projectRecommendations(projection, NOW, [])).toEqual([])
  })

  it('drops expired rows, keeps the first of duplicate dedupe keys, caps at three', () => {
    const projection = wireProjection([
      wireRow({ intervention_id: 'iv-a', dedupe_key: 'dk-a', headline: 'A' }),
      wireRow({ intervention_id: 'iv-exp', dedupe_key: 'dk-exp', expires_at: PAST }),
      wireRow({ intervention_id: 'iv-dup', dedupe_key: 'dk-a', headline: 'A-dup' }),
      wireRow({ intervention_id: 'iv-b', dedupe_key: 'dk-b', headline: 'B' }),
      wireRow({ intervention_id: 'iv-c', dedupe_key: 'dk-c', headline: 'C' }),
      wireRow({ intervention_id: 'iv-d', dedupe_key: 'dk-d', headline: 'D' })
    ])
    const rows = projectRecommendations(projection, NOW, [])
    expect(rows.map((r) => r.headline)).toEqual(['A', 'B', 'C'])
    expect(rows[0].id).toBe('out-1:dk-a')
  })

  it('maps destinations by subject kind and drops artifact rows with no workstream', () => {
    const projection = wireProjection([
      wireRow({ subject_kind: 'candidate', subject_id: 'c-1', dedupe_key: 'k1' }),
      wireRow({
        subject_kind: 'workstream',
        subject_id: 'ws-1',
        destination_task_id: 't-9',
        dedupe_key: 'k2'
      }),
      wireRow({ subject_kind: 'artifact', destination_workstream_id: null, dedupe_key: 'k3' }),
      wireRow({
        subject_kind: 'agent_open_loop',
        destination_workstream_id: 'ws-2',
        dedupe_key: 'k4'
      })
    ])
    const rows = projectRecommendations(projection, NOW, [])
    expect(rows.map((r) => r.destination)).toEqual([
      { kind: 'suggested', candidateId: 'c-1' },
      { kind: 'thread', workstreamId: 'ws-1', taskId: 't-9' },
      { kind: 'thread', workstreamId: 'ws-2', taskId: null }
    ])
  })

  it('unknown subject kinds are dropped, not thrown', () => {
    const projection = wireProjection([wireRow({ subject_kind: 'hologram', dedupe_key: 'k1' })])
    expect(projectRecommendations(projection, NOW, [])).toEqual([])
  })

  it('rows matching a pending later/dismiss outbox entry are suppressed', () => {
    enqueueFeedback({
      request: {
        action: 'dismiss',
        subject_kind: 'task',
        subject_id: 'task-1',
        intervention_id: 'iv-1',
        reason: null,
        later_until: null,
        context_snapshot_hash: null
      },
      idempotencyKey: 'k',
      accountGeneration: 3
    })
    const projection = wireProjection([wireRow()])
    expect(projectRecommendations(projection, NOW, loadOutbox())).toEqual([])
  })
})

describe('load gating', () => {
  it('a non-read workflow mode clears the surface with no error text', async () => {
    const store = makeStore({
      '/v1/candidates/control': { workflow_mode: 'shadow', account_generation: 3 }
    })
    await store.load()
    const s = store.getState()
    expect(s.accountGeneration).toBeNull()
    expect(s.recommendations).toEqual([])
    expect(s.goals).toEqual([])
    expect(s.error).toBeNull()
  })

  it('a 404 what-matters-now clears recommendations silently (capability-gated account)', async () => {
    const store = makeStore({
      '/v1/candidates/control': READ_CONTROL,
      '/v1/goals/canonical/list': [wireGoal()]
    })
    await store.load()
    const s = store.getState()
    expect(s.accountGeneration).toBe(3)
    expect(s.recommendations).toEqual([])
    expect(s.error).toBeNull()
    expect(s.goals).toHaveLength(1)
  })

  it('a live projection lands as projected rows', async () => {
    const store = makeStore({
      '/v1/candidates/control': READ_CONTROL,
      '/v1/what-matters-now': {
        schema_version: 1,
        evaluation_id: 'ev-1',
        output_version: 'out-1',
        material_version: 'mat-1',
        generated_at: PAST,
        expires_at: FUTURE,
        recommendations: [wireRow()]
      },
      '/v1/goals/canonical/list': []
    })
    await store.load()
    expect(store.getState().recommendations.map((r) => r.headline)).toEqual(['Finish the report'])
  })

  it('a non-empty outbox after a clean load shows the retry banner', async () => {
    enqueueFeedback({
      request: {
        action: 'dismiss',
        subject_kind: 'task',
        subject_id: 'x',
        intervention_id: 'iv-x',
        reason: null,
        later_until: null,
        context_snapshot_hash: null
      },
      idempotencyKey: 'stuck',
      accountGeneration: 3
    })
    const store = makeStore({
      '/v1/candidates/control': READ_CONTROL,
      '/v1/goals/canonical/list': [],
      'POST /v1/task-intelligence/feedback': () => {
        throw new Error('still down')
      }
    })
    await store.load()
    expect(store.getState().error).toBe(RETRY_BANNER)
    expect(store.getState().pendingFeedbackCount).toBe(1)
  })

  it('replays the outbox on load and clears delivered entries', async () => {
    enqueueFeedback({
      request: {
        action: 'later',
        subject_kind: 'task',
        subject_id: 'x',
        intervention_id: 'iv-x',
        reason: null,
        later_until: FUTURE,
        context_snapshot_hash: null
      },
      idempotencyKey: 'queued',
      accountGeneration: 3
    })
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = makeStore(
      {
        '/v1/candidates/control': READ_CONTROL,
        '/v1/goals/canonical/list': [],
        'POST /v1/task-intelligence/feedback': {}
      },
      capture
    )
    await store.load()
    expect(capture.posts).toHaveLength(1)
    const [, , config] = capture.posts[0] as [string, unknown, { headers: Record<string, unknown> }]
    expect(config.headers['Idempotency-Key']).toBe('queued')
    expect(config.headers['X-Account-Generation']).toBe(3)
    expect(loadOutbox()).toEqual([])
    expect(store.getState().error).toBeNull()
  })

  it('purges outbox entries from a superseded generation without sending them', async () => {
    enqueueFeedback({
      request: {
        action: 'dismiss',
        subject_kind: 'task',
        subject_id: 'x',
        intervention_id: 'iv-x',
        reason: null,
        later_until: null,
        context_snapshot_hash: null
      },
      idempotencyKey: 'old-gen',
      accountGeneration: 2
    })
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = makeStore(
      {
        '/v1/candidates/control': READ_CONTROL,
        '/v1/goals/canonical/list': []
      },
      capture
    )
    await store.load()
    expect(capture.posts).toHaveLength(0)
    expect(loadOutbox()).toEqual([])
  })
})

async function loadedStore(
  capture?: { posts: unknown[][]; deletes: unknown[][] },
  extra: Routes = {}
) {
  const store = makeStore(
    {
      '/v1/candidates/control': READ_CONTROL,
      '/v1/what-matters-now': {
        schema_version: 1,
        evaluation_id: 'ev-1',
        output_version: 'out-1',
        material_version: 'mat-1',
        generated_at: PAST,
        expires_at: FUTURE,
        recommendations: [wireRow()]
      },
      '/v1/goals/canonical/list': [wireGoal()],
      ...extra
    },
    capture
  )
  await store.load()
  return store
}

describe('feedback actions', () => {
  it('do_now posts a deterministic key and threads the row intervention id', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/task-intelligence/feedback': {} })
    const row = store.getState().recommendations[0]
    await store.recordPrimaryAction(row)
    const feedback = capture.posts.find((p) => p[0] === '/v1/task-intelligence/feedback')
    expect(feedback?.[1]).toEqual({
      action: 'do_now',
      subject_kind: 'task',
      subject_id: 'task-1',
      intervention_id: 'iv-1',
      reason: null,
      later_until: null,
      context_snapshot_hash: null
    })
    const config = feedback?.[2] as { headers: Record<string, unknown> }
    expect(config.headers['Idempotency-Key']).toBe('wmn:iv-1:do-now')
    expect(store.getState().recommendations).toEqual([])
    expect(loadOutbox()).toEqual([])
  })

  it('later sends +24h and a unique-per-occurrence key', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/task-intelligence/feedback': {} })
    await store.later(store.getState().recommendations[0])
    const feedback = capture.posts.find((p) => p[0] === '/v1/task-intelligence/feedback')
    const body = feedback?.[1] as { later_until: string; action: string }
    expect(body.action).toBe('later')
    expect(Date.parse(body.later_until)).toBe(NOW + 24 * 60 * 60 * 1000)
    const config = feedback?.[2] as { headers: Record<string, string> }
    expect(config.headers['Idempotency-Key']).toBe('wmn:iv-1:later:uuid-fixed')
  })

  it("dismiss without a reason keys on the literal 'none'", async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/task-intelligence/feedback': {} })
    await store.dismiss(store.getState().recommendations[0], null)
    const config = capture.posts.find((p) => p[0] === '/v1/task-intelligence/feedback')?.[2] as {
      headers: Record<string, string>
    }
    expect(config.headers['Idempotency-Key']).toBe('wmn:iv-1:dismiss:none')
  })

  it('a failed post still removes the row, keeps the entry queued, and shows the saved banner', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, {
      'POST /v1/task-intelligence/feedback': () => {
        throw new Error('down')
      }
    })
    await store.dismiss(store.getState().recommendations[0], 'not_useful')
    expect(store.getState().recommendations).toEqual([])
    expect(store.getState().error).toBe(FEEDBACK_SAVED_ERROR)
    expect(loadOutbox().map((e) => e.idempotencyKey)).toEqual(['wmn:iv-1:dismiss:not_useful'])
  })
})

describe('canonical goals', () => {
  it('create hardcodes background/user and uses the occurrence id as the idempotency key', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/goals/canonical': wireGoal() })
    const ok = await store.createGoal(
      { title: 'T', desiredOutcome: 'O', whyItMatters: null, successCriteria: ['a'] },
      'occurrence-1'
    )
    expect(ok).toBe(true)
    const create = capture.posts.find((p) => p[0] === '/v1/goals/canonical')
    expect(create?.[1]).toEqual({
      title: 'T',
      desired_outcome: 'O',
      why_it_matters: null,
      success_criteria: ['a'],
      status: 'background',
      source: 'user'
    })
    expect((create?.[2] as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe(
      'occurrence-1'
    )
  })

  it('focus 409 without a replacement exposes the replacement flow', async () => {
    const conflict = new Error('conflict') as Error & { response?: { status: number } }
    conflict.response = { status: 409 }
    const store = await loadedStore(undefined, {
      'POST /v1/goals/g-2/focus': () => {
        throw conflict
      }
    })
    const ok = await store.focus('g-2', null)
    expect(ok).toBe(false)
    expect(store.getState().focusReplacementGoalId).toBe('g-2')
    expect(store.getState().error).toBe(CHOOSE_REPLACEMENT)
  })

  it('focus with a replacement sends it and clears the replacement flow', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/goals/g-2/focus': wireGoal() })
    const ok = await store.focus('g-2', 'g-1')
    expect(ok).toBe(true)
    const focus = capture.posts.find((p) => p[0] === '/v1/goals/g-2/focus')
    expect(focus?.[1]).toEqual({ replacement_goal_id: 'g-1', focus_rank: null })
    expect(store.getState().focusReplacementGoalId).toBeNull()
  })

  it('lifecycle transitions always retain relationships', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/goals/g-1/lifecycle': wireGoal() })
    await store.transition('g-1', 'achieved')
    const call = capture.posts.find((p) => p[0] === '/v1/goals/g-1/lifecycle')
    expect(call?.[1]).toEqual({ status: 'achieved', relationship_disposition: 'retain' })
  })

  it('derived lists split focused, current, and ended', () => {
    const goals = [
      { ...goalFixture('a', 'focused'), focusRank: 1 },
      { ...goalFixture('b', 'focused'), focusRank: 0 },
      goalFixture('c', 'background'),
      goalFixture('d', 'achieved'),
      goalFixture('e', 'abandoned')
    ]
    expect(focusedGoals(goals).map((g) => g.goalId)).toEqual(['b', 'a'])
    expect(currentGoals(goals).map((g) => g.goalId)).toEqual(['a', 'b', 'c'])
    expect(endedGoals(goals).map((g) => g.goalId)).toEqual(['d', 'e'])
  })
})

function goalFixture(id: string, status: string) {
  return {
    goalId: id,
    title: id,
    desiredOutcome: '',
    whyItMatters: null,
    successCriteria: [],
    status: status as never,
    focusRank: null,
    isActive: true,
    updatedAt: '2026-08-01T00:00:00Z',
    currentValue: null,
    targetValue: null,
    unit: null
  }
}

describe('attribution analytics', () => {
  it('emits intervention_presented once per intervention across loads', async () => {
    const routes: Routes = {
      '/v1/candidates/control': READ_CONTROL,
      '/v1/what-matters-now': {
        schema_version: 1,
        evaluation_id: 'ev-1',
        output_version: 'out-1',
        material_version: 'mat-1',
        generated_at: PAST,
        expires_at: FUTURE,
        recommendations: [wireRow()]
      },
      '/v1/goals/canonical/list': []
    }
    const store = makeStore(routes)
    await store.load()
    await store.load()
    const presented = trackEvent.mock.calls.filter(
      (c) => (c[1] as { event_type?: string }).event_type === 'intervention_presented'
    )
    expect(presented).toHaveLength(1)
    expect(presented[0][1]).toMatchObject({
      surface: 'what_matters_now',
      intervention_id: 'iv-1',
      subject_kind: 'task',
      subject_id: 'task-1'
    })
  })

  it('emits feedback_recorded only on server-accepted feedback, with the chain id', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, {
      'POST /v1/task-intelligence/feedback': { attribution_chain_id: 'chain-9' }
    })
    trackEvent.mockClear()
    await store.dismiss(store.getState().recommendations[0], 'not_mine')
    const recorded = trackEvent.mock.calls.filter(
      (c) => (c[1] as { event_type?: string }).event_type === 'feedback_recorded'
    )
    expect(recorded).toHaveLength(1)
    expect(recorded[0][1]).toMatchObject({
      feedback_action: 'dismiss',
      feedback_reason: 'not_mine',
      attribution_chain_id: 'chain-9'
    })
  })

  it('a failed feedback post emits no feedback_recorded event', async () => {
    const store = await loadedStore(undefined, {
      'POST /v1/task-intelligence/feedback': () => {
        throw new Error('down')
      }
    })
    trackEvent.mockClear()
    await store.dismiss(store.getState().recommendations[0], null)
    const recorded = trackEvent.mock.calls.filter(
      (c) => (c[1] as { event_type?: string }).event_type === 'feedback_recorded'
    )
    expect(recorded).toHaveLength(0)
  })
})

describe('openRecommendation', () => {
  it('opens a live row through the handler and records do_now after success', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/task-intelligence/feedback': {} })
    const rowId = store.getState().recommendations[0].id
    const handler = vi.fn(() => true)
    expect(await store.openRecommendation(rowId, handler)).toBe(true)
    expect(handler).toHaveBeenCalledTimes(1)
    const feedback = capture.posts.find((p) => p[0] === '/v1/task-intelligence/feedback')
    expect((feedback?.[1] as { action?: string }).action).toBe('do_now')
  })

  it('a handler that fails to open records no feedback', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/task-intelligence/feedback': {} })
    const rowId = store.getState().recommendations[0].id
    expect(await store.openRecommendation(rowId, () => false)).toBe(false)
    expect(capture.posts.some((p) => p[0] === '/v1/task-intelligence/feedback')).toBe(false)
  })

  it('a missing id reloads once and then surfaces the unavailable error', async () => {
    const store = await loadedStore()
    expect(await store.openRecommendation('out-1:nope', () => true)).toBe(false)
    expect(store.getState().error).toBe(TARGET_UNAVAILABLE)
  })
})

describe('applyContextProjection', () => {
  it('re-projects rows, clears the error, and emits presented for new interventions', async () => {
    const store = await loadedStore(undefined, {
      'POST /v1/task-intelligence/feedback': () => {
        throw new Error('down')
      }
    })
    await store.dismiss(store.getState().recommendations[0], null)
    expect(store.getState().error).toBe(FEEDBACK_SAVED_ERROR)
    trackEvent.mockClear()
    // Clear the pending entry so the re-applied projection is not suppressed.
    window.localStorage.clear()
    const projection = wireProjection([
      wireRow({ intervention_id: 'iv-ctx', dedupe_key: 'dk-ctx', headline: 'From the director' })
    ])
    store.applyContextProjection(projection)
    expect(store.getState().recommendations.map((r) => r.headline)).toEqual(['From the director'])
    expect(store.getState().error).toBeNull()
    const presented = trackEvent.mock.calls.filter(
      (c) => (c[1] as { event_type?: string }).event_type === 'intervention_presented'
    )
    expect(presented).toHaveLength(1)
  })
})

describe('recordTaskOutcome (declared-unused seam)', () => {
  it('posts the outcome wire shape with generation and idempotency headers', async () => {
    const capture = { posts: [] as unknown[][], deletes: [] as unknown[][] }
    const store = await loadedStore(capture, { 'POST /v1/task-intelligence/outcomes': {} })
    const ok = await store.recordTaskOutcome({
      attributionChainId: 'chain-1',
      outcomeCode: 'task_completed',
      subjectKind: 'task',
      subjectId: 'task-1'
    })
    expect(ok).toBe(true)
    const call = capture.posts.find((p) => p[0] === '/v1/task-intelligence/outcomes')
    expect(call?.[1]).toEqual({
      attribution_chain_id: 'chain-1',
      outcome_code: 'task_completed',
      subject_kind: 'task',
      subject_id: 'task-1'
    })
    const headers = (call?.[2] as { headers: Record<string, unknown> }).headers
    expect(headers['Idempotency-Key']).toBe('wmn-outcome:chain-1:task_completed')
    expect(headers['X-Account-Generation']).toBe(3)
  })

  it('refuses outside the rollout (no bound generation)', async () => {
    const store = makeStore({
      '/v1/candidates/control': { workflow_mode: 'off', account_generation: 0 }
    })
    await store.load()
    expect(
      await store.recordTaskOutcome({
        attributionChainId: 'chain-1',
        outcomeCode: 'task_completed',
        subjectKind: 'task',
        subjectId: 'task-1'
      })
    ).toBe(false)
  })
})

describe('owner switching', () => {
  it('a sign-out/in between loads clears every owner-scoped piece before loading', async () => {
    let owner = 'uid-1'
    const store = new DashboardIntelligenceStore({
      get: vi.fn(async (path: string) => {
        if (path === '/v1/candidates/control') return { data: READ_CONTROL }
        if (path === '/v1/goals/canonical/list') return { data: [wireGoal()] }
        const err = new Error('nf') as Error & { response?: { status: number } }
        err.response = { status: 404 }
        throw err
      }) as never,
      post: vi.fn() as never,
      del: vi.fn() as never,
      now: () => NOW,
      uuid: () => 'u',
      ownerId: () => owner
    })
    await store.load()
    expect(store.getState().goals).toHaveLength(1)

    owner = 'uid-2'
    const cleared = store.load()
    // The switch clears synchronously before the new owner's fetch lands.
    expect(store.getState().goals).toEqual([])
    expect(store.getState().accountGeneration).toBeNull()
    await cleared
    expect(store.getState().accountGeneration).toBe(3)
  })
})

describe('control failure during refresh', () => {
  it('clears the generation and rows so stale recommendations are never actionable', async () => {
    let controlFails = false
    const store = new DashboardIntelligenceStore({
      get: vi.fn(async (path: string) => {
        if (path === '/v1/candidates/control') {
          if (controlFails) throw new Error('down')
          return { data: READ_CONTROL }
        }
        if (path === '/v1/what-matters-now') {
          return {
            data: {
              schema_version: 1,
              evaluation_id: 'ev-1',
              output_version: 'out-1',
              material_version: 'mat-1',
              generated_at: PAST,
              expires_at: FUTURE,
              recommendations: [wireRow()]
            }
          }
        }
        if (path === '/v1/goals/canonical/list') return { data: [] }
        const err = new Error('nf') as Error & { response?: { status: number } }
        err.response = { status: 404 }
        throw err
      }) as never,
      post: vi.fn() as never,
      del: vi.fn() as never,
      now: () => NOW,
      uuid: () => 'u',
      ownerId: () => 'uid-1'
    })
    await store.load()
    expect(store.getState().recommendations).toHaveLength(1)

    controlFails = true
    await store.load()
    expect(store.getState().accountGeneration).toBeNull()
    expect(store.getState().recommendations).toEqual([])
    expect(store.getState().error).toBe('Recommendations are unavailable right now.')
  })
})
