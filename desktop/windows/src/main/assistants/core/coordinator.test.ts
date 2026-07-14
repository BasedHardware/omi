// The framework's contract, exercised end-to-end through a trivial no-op
// assistant: registered → gated → analyzed → result handled, with the
// backpressure, privacy, context-switch and cadence rules around it.
//
// Every impure edge is injected (clock, frame source, settings, power), so this
// runs with no timers, no DB and no Electron. `../../ipc/db` is mocked away for
// the same reason every other main-side suite does: importing it would load the
// better-sqlite3 native binding.
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../ipc/db', () => ({ latestRewindFrame: vi.fn(() => null) }))
vi.mock('../../appSettings', () => ({
  getAppSettings: vi.fn(() => ({ screenAnalysisEnabled: true }))
}))

import {
  AssistantCoordinator,
  type CoordinatorDeps,
  type ProactiveAssistant,
  type SendEvent
} from './coordinator'
import type { RewindFrame } from '../../../shared/types'

const T0 = 1_700_000_000_000

function frame(over: Partial<RewindFrame> = {}): RewindFrame {
  return {
    id: 1,
    ts: T0,
    app: 'Visual Studio Code',
    windowTitle: 'index.ts — omi',
    processName: 'code',
    ocrText: '', // empty at insert — the async backfiller fills it later
    imagePath: 'C:/frames/1.jpg',
    width: 1920,
    height: 1080,
    indexed: 0,
    ...over
  }
}

/** The trivial no-op assistant: records what the framework handed it. */
class TestAssistant implements ProactiveAssistant {
  readonly identifier: string
  readonly displayName = 'Test'
  enabled = true
  needsDelayFrames = false
  analyzed: RewindFrame[] = []
  handled: Record<string, unknown>[] = []
  switches: { departing: RewindFrame | null; app: string; title: string }[] = []
  cleared = 0
  stopped = 0
  shouldAnalyzeCalls: { frameNumber: number; since: number }[] = []
  shouldAnalyzeResult = true
  /** While set, analyze() hangs — that's how a test holds the in-flight slot. */
  private gate: Promise<void> | null = null

  constructor(identifier = 'test') {
    this.identifier = identifier
  }

  /** Make analyze() hang; the returned function lets it finish. */
  hangUntilReleased(): () => void {
    let release!: () => void
    this.gate = new Promise<void>((r) => (release = r))
    return () => {
      release()
      this.gate = null
    }
  }

  isEnabled(): boolean {
    return this.enabled
  }
  shouldAnalyze(frameNumber: number, since: number): boolean {
    this.shouldAnalyzeCalls.push({ frameNumber, since })
    return this.shouldAnalyzeResult
  }
  needsFrameDuringDelay(): boolean {
    return this.needsDelayFrames
  }
  async analyze(f: RewindFrame): Promise<Record<string, unknown> | null> {
    this.analyzed.push(f)
    if (this.gate) await this.gate
    return { ok: true }
  }
  handleResult(result: Record<string, unknown>, _sendEvent: SendEvent): void {
    this.handled.push(result)
  }
  onContextSwitch(departing: RewindFrame | null, app: string, title: string): void {
    this.switches.push({ departing, app, title })
  }
  clearPendingWork(): void {
    this.cleared += 1
  }
  stop(): void {
    this.stopped += 1
  }
}

let now = T0
let latest: RewindFrame | null = null
let onBattery = false
let enabled = true

function make(over: Partial<CoordinatorDeps> = {}): AssistantCoordinator {
  return new AssistantCoordinator({
    latestFrame: () => latest,
    now: () => now,
    isOnBattery: () => onBattery,
    isScreenAnalysisEnabled: () => enabled,
    analysisDelayMs: () => 60_000,
    ...over
  })
}

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  now = T0
  latest = null
  onBattery = false
  enabled = true
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

describe('plumbing (no-op assistant, end to end)', () => {
  it('registered → gated → analyze → handleResult', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame()
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(1)
    expect(a.handled).toEqual([{ ok: true }])
    // Seeded to -Infinity, so the first frame reads as "never analyzed".
    expect(a.shouldAnalyzeCalls[0]).toEqual({ frameNumber: 1, since: Infinity })
  })

  it('routes results through the coordinator event callback', async () => {
    const c = make()
    const events: [string, Record<string, unknown>][] = []
    c.setEventCallback((type, data) => events.push([type, data]))
    const a = new TestAssistant()
    // Emit an event from handleResult, the way a real assistant would.
    a.handleResult = (result, sendEvent): void => sendEvent('test:done', result)
    c.register(a)

    latest = frame()
    c.tick()
    await flush()

    expect(events).toEqual([['test:done', { ok: true }]])
  })

  it('skips a disabled assistant', async () => {
    const c = make()
    const a = new TestAssistant()
    a.enabled = false
    c.register(a)

    latest = frame()
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(0)
  })

  it('honours the assistant’s own shouldAnalyze, and does not reset its cadence clock on a decline', async () => {
    const c = make()
    const a = new TestAssistant()
    a.shouldAnalyzeResult = false
    c.register(a)

    latest = frame({ id: 1 })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(0)

    now = T0 + 5_000
    latest = frame({ id: 2 })
    c.tick()
    await flush()

    // Still "never analyzed" — a declined frame must not look like a run.
    expect(a.shouldAnalyzeCalls[1]).toEqual({ frameNumber: 2, since: Infinity })
  })

  it('stopAll stops every assistant', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)
    await c.stopAll()
    expect(a.stopped).toBe(1)
  })
})

describe('master toggle', () => {
  it('reads no frame at all while screen analysis is off', () => {
    const reader = vi.fn(() => frame())
    const c = make({ latestFrame: reader })
    c.register(new TestAssistant())
    enabled = false

    c.tick()

    expect(reader).not.toHaveBeenCalled()
  })

  it('start() does not arm a timer while the toggle is off', () => {
    const c = make()
    enabled = false
    c.start()
    expect(c.isRunning()).toBe(false)
    c.stop()
  })
})

describe('backpressure', () => {
  it('skips a busy assistant instead of queueing frames behind it', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)
    const release = a.hangUntilReleased()

    latest = frame({ id: 1 })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1) // in flight, hanging

    latest = frame({ id: 2 })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1) // skipped, NOT queued

    release()
    await flush()

    // Free again → the next frame is analyzed.
    latest = frame({ id: 3 })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(2)
    expect(a.analyzed[1].id).toBe(3)
  })

  it('a busy assistant does not block its peers on the same frame', async () => {
    const c = make()
    const busy = new TestAssistant()
    const other = new TestAssistant('other')
    c.register(busy)
    c.register(other)
    const release = busy.hangUntilReleased()

    latest = frame({ id: 1 })
    c.tick()
    await flush()

    latest = frame({ id: 2 })
    c.tick()
    await flush()

    expect(busy.analyzed).toHaveLength(1)
    expect(other.analyzed).toHaveLength(2)
    release()
  })

  it('does not re-analyze the same frame row (capture paused while the user is idle)', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 7 })
    c.tick()
    c.tick()
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(1)
  })
})

describe('privacy gate', () => {
  it('never hands a denied frame to an assistant', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Google Chrome', windowTitle: 'Chase — Accounts' })
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(0)
  })

  it('passes a denied frame’s context switch through, but never its pixels — even as a departing frame', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    latest = frame({ id: 2, app: 'Google Chrome', windowTitle: 'Chase — Accounts' })
    c.tick()
    await flush()

    // The move to the bank IS a context switch (assistants must know the user
    // left Slack) — but the departing frame is the Slack one, and the bank frame
    // is never analyzed.
    expect(a.switches).toHaveLength(1)
    expect(a.switches[0].departing?.app).toBe('Slack')
    expect(a.analyzed.map((f) => f.app)).toEqual(['Slack'])
  })
})

describe('context switch + analysis delay', () => {
  it('fires onContextSwitch with the departing frame, clears pending work, and quiets analysis', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1)

    now = T0 + 3_000
    latest = frame({ id: 2, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick()
    await flush()

    expect(a.switches).toEqual([
      { departing: expect.objectContaining({ id: 1 }), app: 'Chrome', title: 'Docs' }
    ])
    expect(a.cleared).toBe(1)
    // Inside the 60s quiet window → the switching frame is not analyzed.
    expect(a.analyzed).toHaveLength(1)

    // Still quiet 59s later...
    now = T0 + 59_000
    latest = frame({ id: 3, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1)

    // ...and analysis resumes once the delay has elapsed.
    now = T0 + 64_000
    latest = frame({ id: 4, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(2)
  })

  it('feeds an opted-in assistant during the delay', async () => {
    const c = make()
    const a = new TestAssistant()
    a.needsDelayFrames = true
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    now = T0 + 3_000
    latest = frame({ id: 2, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(2)
  })

  it('does not extend the quiet window when the user keeps app-hopping', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    now = T0 + 1_000
    latest = frame({ id: 2, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick() // switch → quiet until T0+61s
    await flush()

    now = T0 + 30_000
    latest = frame({ id: 3, ts: now, app: 'Slack', windowTitle: 'general' })
    c.tick() // another switch, mid-quiet → must NOT push the window out
    await flush()

    now = T0 + 62_000
    latest = frame({ id: 4, ts: now, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(2) // frame 1, then frame 4
    expect(a.switches).toHaveLength(2) // both switches still reported
  })

  it('does not treat a spinner/timer title change as a switch', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Terminal', windowTitle: '⠋ Building — 00:01' })
    c.tick()
    await flush()

    now = T0 + 3_000
    latest = frame({ id: 2, ts: now, app: 'Terminal', windowTitle: '⣾ Building — 00:04' })
    c.tick()
    await flush()

    expect(a.switches).toHaveLength(0)
    expect(a.analyzed).toHaveLength(2) // no quiet window → analysis continues
  })
})

describe('cadence', () => {
  it('is 3s on mains and 9s on battery', () => {
    const c = make()
    expect(c.intervalMs()).toBe(3_000)
    onBattery = true
    expect(c.intervalMs()).toBe(9_000)
  })
})
