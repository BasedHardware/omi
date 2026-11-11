// The promotion safety net (Mac's TaskPromotionService.start() port): the 60s
// bypass-debounce timer + the startup promote, and the batch-strand regression
// (P1-4) they fix. Hermetic — fake net.fetch with a FIFO staged-task backend, fake
// timers (so the 30s inline debounce and the 60s safety timer advance on the same
// clock), injected storage/embedding/session. Uses the REAL create.ts
// promoteIfNeeded + its module-level debounce state, so the service and create.ts
// share exactly one `lastPromotedAt`/`promotionInFlight` — the point of the design.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RewindFrame } from '../../../shared/types'
import type { ExtractedTask } from './models'

// A realistic wall-clock base so the FIRST promote isn't self-debounced: create.ts's
// `lastPromotedAt` resets to 0 (epoch 1970), and the debounce is `Date.now() -
// lastPromotedAt < 30s`. At a 1970 clock the first fire would (wrongly) debounce;
// in production Date.now() is ~1.7e12 so it never does. Mirror production here.
const T0 = 1_700_000_000_000

const h = vi.hoisted(() => ({
  epoch: 5,
  session: { apiBase: 'https://api', desktopApiBase: 'https://d', token: 't' } as unknown,
  getSessionEpoch: vi.fn(),
  getBackendSession: vi.fn(),
  getAbortSignal: vi.fn(() => undefined),
  insertLocalStagedTask: vi.fn(),
  markSyncedStagedTask: vi.fn(),
  syncTaskActionItems: vi.fn(),
  generateEmbeddingForTask: vi.fn(async () => {}),
  fetch: vi.fn(),
  send: vi.fn()
}))

vi.mock('../core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession,
  getAbortSignal: h.getAbortSignal
}))
vi.mock('../../ipc/db', () => ({
  insertLocalStagedTask: h.insertLocalStagedTask,
  markSyncedStagedTask: h.markSyncedStagedTask,
  syncTaskActionItems: h.syncTaskActionItems
}))
vi.mock('../../tasks/taskEmbeddingService', () => ({
  generateEmbeddingForTask: h.generateEmbeddingForTask
}))
vi.mock('electron', () => ({
  net: { fetch: h.fetch },
  BrowserWindow: {
    getAllWindows: () => [{ isDestroyed: () => false, webContents: { send: h.send } }]
  }
}))

import {
  createStagedTaskFromExtraction,
  promoteIfNeeded,
  __resetPromotionStateForTests
} from './create'
import {
  startTaskPromotionService,
  stopTaskPromotionService,
  __resetPromotionServiceForTests
} from './promotionService'

// --- FIFO fake backend -------------------------------------------------------
// `POST /v1/staged-tasks` pushes an id; `POST /v1/staged-tasks/promote` pops the
// front one and returns {promoted:true, promoted_task} (exact router shape), or
// {promoted:false} when empty. `promotePostCount` counts only REAL promote POSTs —
// a debounced promoteIfNeeded returns before the fetch, so it never increments.
let stagedQueue: string[] = []
let stagedSeq = 0
let localSeq = 0
let promotePostCount = 0
// Optional deferral seam for the mid-promote epoch-change test.
let deferPromote: { resolve: (v: unknown) => void } | null = null

function fifoRoute(): void {
  h.fetch.mockImplementation(async (url: string) => {
    if (url.endsWith('/v1/staged-tasks/promote')) {
      promotePostCount += 1
      const id = stagedQueue.shift()
      const body = id
        ? {
            promoted: true,
            reason: null,
            promoted_task: { id: `ai-${id}`, description: `desc ${id}`, completed: false }
          }
        : { promoted: false, reason: 'No staged tasks available', promoted_task: null }
      if (deferPromote) {
        const d = deferPromote
        deferPromote = null
        return new Promise((resolve) => {
          d.resolve = (): void => resolve({ ok: true, json: async () => body })
        })
      }
      return { ok: true, json: async () => body }
    }
    if (url.endsWith('/v1/staged-tasks')) {
      const id = `st-${(stagedSeq += 1)}`
      stagedQueue.push(id)
      return { ok: true, json: async () => ({ id }) }
    }
    return { ok: false, status: 404, json: async () => ({}) }
  })
}

// --- Fixtures ----------------------------------------------------------------
const baseTask: ExtractedTask = {
  title: 'placeholder',
  description: 'reason',
  priority: 'high',
  sourceApp: 'Slack',
  inferredDeadline: null,
  confidence: 0.9,
  tags: ['work'],
  sourceCategory: 'direct_request',
  sourceSubcategory: 'message',
  captureKind: 'clear_commitment',
  owner: 'user',
  concreteDeliverable: true,
  publicBroadcast: false,
  directMention: true,
  alreadyDone: false,
  duplicateOf: null,
  refinesTask: null,
  ownershipConfidence: 0.85,
  contextSummary: 'ctx',
  currentActivity: 'act'
}
const makeTask = (title: string): ExtractedTask => ({ ...baseTask, title })

const frame: RewindFrame = {
  id: 7,
  ts: 1000,
  app: 'Slack',
  windowTitle: 'Acme — general',
  processName: 'slack',
  ocrText: '',
  imagePath: '',
  width: 0,
  height: 0,
  indexed: 1
}

/** Distinct promoted backendIds seen by the local store, in order. */
const promotedBackendIds = (): string[] =>
  h.syncTaskActionItems.mock.calls.map((c) => (c[0] as Array<{ backendId: string }>)[0].backendId)

const broadcastCount = (): number =>
  h.send.mock.calls.filter(([ch]) => ch === 'tasks:changed').length

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(T0)
  vi.clearAllMocks()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'log').mockImplementation(() => {})
  h.epoch = 5
  h.session = { apiBase: 'https://api', desktopApiBase: 'https://d', token: 't' }
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.getBackendSession.mockImplementation(() => h.session)
  h.getAbortSignal.mockReturnValue(undefined)
  h.insertLocalStagedTask.mockImplementation(() => ({ id: (localSeq += 1) }))
  h.markSyncedStagedTask.mockReset()
  h.syncTaskActionItems.mockReturnValue({ skipped: 0, adopted: 0, inserted: 1, updated: 0 })
  h.generateEmbeddingForTask.mockResolvedValue(undefined)
  stagedQueue = []
  stagedSeq = 0
  localSeq = 0
  promotePostCount = 0
  deferPromote = null
  fifoRoute()
  __resetPromotionStateForTests()
  __resetPromotionServiceForTests()
})

afterEach(() => {
  __resetPromotionServiceForTests()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('T-A — batch-strand regression (the P1-4 bug: FAILS without the safety timer)', () => {
  it('drains all tasks a single frame stages, one per 60s tick', async () => {
    // 1. Stage 3 tasks in one "frame" (exactly taskAssistant.ts:257–264).
    await createStagedTaskFromExtraction(makeTask('task A'), frame, 5)
    await createStagedTaskFromExtraction(makeTask('task B'), frame, 5)
    await createStagedTaskFromExtraction(makeTask('task C'), frame, 5)

    // 2. Current (inline-only) behavior: task A promoted inline; B and C are
    //    debounced (<30s since A) → stranded in the FIFO. THIS is the bug.
    expect(promotePostCount).toBe(1)
    expect(promotedBackendIds()).toEqual(['ai-st-1'])
    expect(stagedQueue).toEqual(['st-2', 'st-3'])

    // 3. Start the safety net (session present).
    startTaskPromotionService()

    // 4. Each 60s tick promotes one stranded task via bypassDebounce.
    await vi.advanceTimersByTimeAsync(60_000)
    expect(promotedBackendIds()).toEqual(['ai-st-1', 'ai-st-2'])
    await vi.advanceTimersByTimeAsync(60_000)
    expect(promotedBackendIds()).toEqual(['ai-st-1', 'ai-st-2', 'ai-st-3'])

    // 5. Core assertion: all 3 distinct backendIds reached the local store, and a
    //    tasks:changed broadcast fired for each promote.
    expect(new Set(promotedBackendIds())).toEqual(new Set(['ai-st-1', 'ai-st-2', 'ai-st-3']))
    expect(broadcastCount()).toBe(3)

    // 6. Empty FIFO → promoted:false: no local write, no broadcast, debounce NOT
    //    re-armed (a promoted:false must not push lastPromotedAt forward).
    await vi.advanceTimersByTimeAsync(60_000)
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(3) // no new write
    expect(broadcastCount()).toBe(3) // no new broadcast

    // Prove lastPromotedAt was not re-armed by the false tick: a NON-bypass promote
    // now (60s after the last real promote at T0+120s) must still fire. If the false
    // tick had re-armed it to T0+180s, this would be debounced and never promote.
    stagedQueue.push('late')
    await promoteIfNeeded()
    expect(promotedBackendIds()).toContain('ai-late')
  })
})

describe('T-B — startup promote', () => {
  it('fires once when a late session appears, without a 60s tick, then the poll stops', async () => {
    stagedQueue.push('st-pre') // staged while the app was closed
    h.session = null // renderer has not relayed the session yet

    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(5_000) // one poll attempt, still signed out
    expect(promotePostCount).toBe(0)

    h.session = { apiBase: 'https://api', desktopApiBase: 'https://d', token: 't' }
    await vi.advanceTimersByTimeAsync(5_000) // next poll sees the session
    // Promoted within ~seconds of sign-in — NO 60s tick has elapsed (t = T0+10s).
    expect(promotePostCount).toBe(1)
    expect(promotedBackendIds()).toEqual(['ai-st-pre'])

    // The poll stopped after firing: advancing 5 more minutes over an empty FIFO
    // yields only safety ticks (all promoted:false), no poll re-fires. Each of those
    // finds nothing and steps down the backoff ladder (60s, then 120s, then 300s), so
    // the window buys 2 ticks. The guard here is the poll — 60 five-second poll
    // attempts would show up as ~60 posts, not 2.
    const postsBefore = promotePostCount
    await vi.advanceTimersByTimeAsync(5 * 60_000)
    const ticks = promotePostCount - postsBefore
    expect(ticks).toBe(2)
    expect(promotedBackendIds()).toEqual(['ai-st-pre']) // nothing left to promote
  })

  it('fires immediately when a session is already present at start', async () => {
    stagedQueue.push('st-now')
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0) // flush the immediate fire (no 60s tick)
    expect(promotePostCount).toBe(1)
    expect(promotedBackendIds()).toEqual(['ai-st-now'])
  })
})

describe('T-C — safety-timer bypass semantics', () => {
  it('promotes a task staged INSIDE the 30s debounce window; a default promote does not', async () => {
    // Inline-stage 1 task at t=T0 (promotes, arms the 30s debounce).
    await createStagedTaskFromExtraction(makeTask('task A'), frame, 5)
    expect(promotedBackendIds()).toEqual(['ai-st-1'])
    startTaskPromotionService()

    // A 2nd staged row appears server-side at t=T0+55s (no inline promote).
    await vi.advanceTimersByTimeAsync(55_000)
    stagedQueue.push('st-hot')

    // The tick at t=T0+60s is only 5s after the last promote — a default-debounce
    // trigger would skip, but bypassDebounce promotes it anyway.
    await vi.advanceTimersByTimeAsync(5_000)
    expect(promotedBackendIds()).toEqual(['ai-st-1', 'ai-st-hot'])

    // Counter-check: a NON-bypass promote 1s after the tick IS debounced.
    stagedQueue.push('st-cold')
    await promoteIfNeeded() // t = T0+60s, 0s since the tick's promote → debounced
    expect(promotedBackendIds()).toEqual(['ai-st-1', 'ai-st-hot']) // st-cold NOT promoted
    expect(stagedQueue).toEqual(['st-cold'])
  })
})

describe('T-D — safety-net backoff (idle request volume)', () => {
  // The regression: a flat 60s timer POSTed /v1/staged-tasks/promote 1,440x/day per
  // client, essentially all returning promoted:false, each costing the backend two
  // full collection scans to answer "nothing".
  it('steps 60s -> 2m -> 5m -> 10m and holds at 10m while nothing is stageable', async () => {
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0) // startup promote (empty FIFO, no post)
    const at = (): number => promotePostCount

    // Each tick lands exactly at the ladder delay, and NOT one millisecond earlier.
    for (const delay of [60_000, 120_000, 300_000, 600_000]) {
      const before = at()
      await vi.advanceTimersByTimeAsync(delay - 1)
      expect(at()).toBe(before) // still armed
      await vi.advanceTimersByTimeAsync(1)
      expect(at()).toBe(before + 1) // fired
    }

    // Ladder is capped, not unbounded: the next tick is 10m again, not 20m.
    const before = at()
    await vi.advanceTimersByTimeAsync(600_000 - 1)
    expect(at()).toBe(before)
    await vi.advanceTimersByTimeAsync(1)
    expect(at()).toBe(before + 1)

    // An idle hour costs single digits, where the flat timer cost 60.
    expect(at()).toBeLessThanOrEqual(8)
  })

  it('a promote resets to the 60s floor, so a backlog still drains one per minute', async () => {
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0)

    // Walk down to the slow end of the ladder over an empty FIFO.
    await vi.advanceTimersByTimeAsync(60_000 + 120_000 + 300_000)
    const posts = promotePostCount

    // Something is staged out of band and the next (10m) tick finds it.
    stagedQueue.push('st-remote')
    await vi.advanceTimersByTimeAsync(600_000)
    expect(promotedBackendIds()).toEqual(['ai-st-remote'])
    expect(promotePostCount).toBe(posts + 1)

    // Reset proof: a second out-of-band row is picked up on the very next MINUTE,
    // not 10 minutes later. Without the reset this assertion fails.
    stagedQueue.push('st-remote-2')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(promotedBackendIds()).toEqual(['ai-st-remote', 'ai-st-remote-2'])
  })

  it('a failing backend backs off instead of retrying at a flat 60s forever', async () => {
    h.fetch.mockImplementation(async () => ({ ok: false, status: 500, json: async () => ({}) }))
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0)

    // One hour against a hard-failing promote endpoint.
    await vi.advanceTimersByTimeAsync(60 * 60_000)
    // Flat-60s behavior would be ~60 posts. The ladder caps the hour in single digits.
    expect(promotePostCount).toBeLessThanOrEqual(8)
  })

  it('a signed-out stretch does not strand a returning user on the slow cadence', async () => {
    // Walk the ladder to its slow end WHILE SIGNED IN first — a service that starts
    // signed out is already at the floor, so it would prove nothing about the reset.
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(60_000 + 120_000 + 300_000) // now on the 10m rung

    h.session = null
    const postsBefore = promotePostCount
    await vi.advanceTimersByTimeAsync(30 * 60_000) // half an hour signed out
    expect(promotePostCount).toBe(postsBefore) // signed out costs nothing

    // Signed-out ticks prove nothing about the backlog, so they must return the net to
    // the floor: a row staged while away is picked up a minute after sign-in, not ten.
    h.session = { apiBase: 'https://api', desktopApiBase: 'https://d', token: 't' }
    stagedQueue.push('st-after-signin')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(promotedBackendIds()).toEqual(['ai-st-after-signin'])
  })
})

describe('T-E — safety negatives', () => {
  it('a timer tick with no session makes zero network calls', async () => {
    h.session = null
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(60_000) // safety tick + poll attempts, all signed out
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('an epoch change mid-promote during a tick writes nothing', async () => {
    // Let the startup promote drain st-race normally first...
    stagedQueue.push('st-race')
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0)
    expect(promotedBackendIds()).toEqual(['ai-st-race'])

    // ...then race the NEXT (tick) promote against a sign-out. `gate` is held by the
    // test (fifoRoute nulls the module `deferPromote`, so we keep our own handle).
    const gate: { resolve: (v: unknown) => void } = { resolve: () => {} }
    stagedQueue.push('st-race2')
    deferPromote = gate
    await vi.advanceTimersByTimeAsync(60_000) // tick fires, promote POST is pending

    h.epoch = 6 // sign-out / user switch while the promote is in flight
    gate.resolve(undefined) // let the response land into the departed epoch
    await vi.advanceTimersByTimeAsync(0)

    // The racing promote's write was dropped by the epoch guard — only the startup
    // promote's write survives.
    expect(promotedBackendIds()).toEqual(['ai-st-race'])
  })

  it('a stop that lands mid-promote does not leave the timer re-armed', async () => {
    // The tick re-arms from inside its own promise chain, so a stop while a promote is
    // in flight must not be undone by that chain finishing afterwards.
    const gate: { resolve: (v: unknown) => void } = { resolve: () => {} }
    stagedQueue.push('st-inflight')
    startTaskPromotionService()
    await vi.advanceTimersByTimeAsync(0) // startup promote drains it
    stagedQueue.push('st-next')
    deferPromote = gate
    await vi.advanceTimersByTimeAsync(60_000) // tick fires, POST pending

    stopTaskPromotionService()
    gate.resolve(undefined)
    await vi.advanceTimersByTimeAsync(0)

    const after = promotePostCount
    await vi.advanceTimersByTimeAsync(60 * 60_000) // an hour with the service stopped
    expect(promotePostCount).toBe(after)
  })

  it('starting twice runs a single safety interval (idempotent)', async () => {
    stagedQueue.push('st-1', 'st-2', 'st-3')
    startTaskPromotionService()
    startTaskPromotionService() // second call must be a no-op
    await vi.advanceTimersByTimeAsync(0) // flush the single startup promote
    const before = promotePostCount
    await vi.advanceTimersByTimeAsync(60_000) // one 60s window → one tick if single interval
    expect(promotePostCount - before).toBe(1)
  })
})
