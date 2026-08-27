import { describe, it, expect, beforeEach } from 'vitest'
import {
  ContextVisitCoordinator,
  type VisitCoordinatorDeps,
  GC_INTERVAL_MS
} from './visitCoordinator'
import type { ContextVisitFence, StartVisitInput } from '../../ipc/contextBucketStore'

const T0 = 1_760_000_000_000

let calls: string[]
let nowMs: number
let nextVisitId: number
let finalizeResult: boolean

function makeDeps(): VisitCoordinatorDeps {
  return {
    startVisit(input: StartVisitInput): ContextVisitFence {
      calls.push(`start:${input.appName}:gen${input.contextGeneration}`)
      return {
        visitID: nextVisitId++,
        contextGeneration: input.contextGeneration,
        poolEpoch: input.poolEpoch,
        bucketID: 'b',
        startedAt: input.startedAt
      }
    },
    finalizeVisit(fence, opts) {
      calls.push(`finalize:${fence.visitID}:${opts.outcome}:${opts.exitReason}`)
      return finalizeResult
    },
    reconcileInterruptedVisits() {
      calls.push('reconcileVisits')
      return 0
    },
    reconcileAbandonedDeliveries() {
      calls.push('reconcileDeliveries')
      return 0
    },
    runDeterministicGC() {
      calls.push('gc')
    },
    poolEpoch: () => 1,
    now: () => nowMs
  }
}

const input = (app = 'Code', title: string | null = 'file.ts') => ({
  toApp: app,
  toWindowTitle: title,
  handles: [],
  processName: null,
  departingFrameId: 7
})

beforeEach(() => {
  calls = []
  nowMs = T0
  nextVisitId = 1
  finalizeResult = true
})

describe('ContextVisitCoordinator', () => {
  it('reconciles and GCs once on the first transition, then opens the visit', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    const result = await coordinator.transition(input())
    expect(calls).toEqual(['reconcileVisits', 'reconcileDeliveries', 'gc', 'start:Code:gen1'])
    expect(result.departed).toBeNull()
    expect(result.arriving.visitID).toBe(1)
  })

  it('qualifies departures at 1 second dwell: below discards, at-or-above completes', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    await coordinator.transition(input('A'))
    nowMs += 500
    const short = await coordinator.transition(input('B'))
    expect(short.departed?.outcome).toBe('discarded')
    nowMs += 1_000
    const long = await coordinator.transition(input('C'))
    expect(long.departed?.outcome).toBe('completed')
    expect(calls).toContain('finalize:1:discarded:context_switch')
    expect(calls).toContain('finalize:2:completed:context_switch')
  })

  it('runs GC again only after the 24h interval', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    await coordinator.transition(input('A'))
    nowMs += 60_000
    await coordinator.transition(input('B'))
    expect(calls.filter((c) => c === 'gc').length).toBe(1)
    nowMs += GC_INTERVAL_MS
    await coordinator.transition(input('C'))
    expect(calls.filter((c) => c === 'gc').length).toBe(2)
  })

  it('excluded contexts close the visit without opening a new one', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    await coordinator.transition(input())
    nowMs += 5_000
    await coordinator.leaveForExcludedContext(9)
    expect(calls).toContain('finalize:1:completed:excluded_context')
    expect(coordinator.activeFence()).toBeNull()
  })

  it('sleep interrupt is guarded against events older than the visit', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    await coordinator.transition(input())
    await coordinator.interruptForSleep(T0 - 1_000)
    expect(calls.some((c) => c.includes('interrupted'))).toBe(false)
    await coordinator.interruptForSleep(nowMs + 1)
    expect(calls).toContain('finalize:1:interrupted:system_sleep')
  })

  it('rearm after resume finalizes leftovers with system_resume and opens fresh', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    await coordinator.transition(input('A'))
    nowMs += 5_000
    const fence = await coordinator.rearmAfterSystemResume(input('A'))
    expect(calls).toContain('finalize:1:completed:system_resume')
    expect(fence.contextGeneration).toBe(2)
  })

  it('a stale finalize re-reconciles in the SAME turn so the replacement survives', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    await coordinator.transition(input('A'))
    calls = []
    finalizeResult = false
    nowMs += 5_000
    const result = await coordinator.transition(input('B'))
    expect(result.departed).toBeNull()
    // The sweep ran BEFORE the replacement opened, so the fresh visit is not
    // the sweep's next victim.
    expect(calls).toEqual([
      'finalize:1:completed:context_switch',
      'reconcileVisits',
      'reconcileDeliveries',
      'gc',
      'start:B:gen2'
    ])
    finalizeResult = true
    calls = []
    nowMs += 5_000
    await coordinator.transition(input('C'))
    // Already reconciled: the next turn goes straight to finalize+start.
    expect(calls).toEqual(['finalize:2:completed:context_switch', 'start:C:gen3'])
  })

  it('serializes concurrent transitions in order', async () => {
    const coordinator = new ContextVisitCoordinator(makeDeps())
    const [a, b] = await Promise.all([
      coordinator.transition(input('A')),
      coordinator.transition(input('B'))
    ])
    expect(a.arriving.contextGeneration).toBe(1)
    expect(b.arriving.contextGeneration).toBe(2)
    expect(b.departed?.fence.visitID).toBe(a.arriving.visitID)
  })
})
