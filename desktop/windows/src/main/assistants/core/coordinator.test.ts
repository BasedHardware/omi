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
  getAppSettings: vi.fn(() => ({ screenAnalysisEnabled: true })),
  onAppSettingsChanged: vi.fn(() => () => {})
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

    now = T0 + 60_000 // past the distribution gate's fallback → a second frame is offered
    latest = frame({ id: 2 })
    c.tick()
    await flush()

    // Still "never analyzed" — a declined frame must not look like a run.
    expect(a.shouldAnalyzeCalls[1]).toEqual({ frameNumber: 2, since: Infinity })
  })

  it('stopAll stops every assistant and forgets them', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1 })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1)

    await c.stopAll()
    expect(a.stopped).toBe(1)

    // A later start() must not resume feeding an assistant we told to stop.
    now = T0 + 120_000
    latest = frame({ id: 2, ts: now })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1)
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

  // The toggle must not be one-way: turning it back on re-arms the loop (the
  // settings listener in registerAssistant is what calls start() again).
  it('re-arms when the toggle goes back on', () => {
    const c = make()
    enabled = false
    c.start()
    expect(c.isRunning()).toBe(false)

    enabled = true
    c.start()
    expect(c.isRunning()).toBe(true)
    c.stop()
  })
})

describe('backpressure', () => {
  // Each step jumps a full fallback interval so the distribution gate offers the
  // frame — backpressure is what we're isolating here, not the gate.
  async function offerFrame(c: AssistantCoordinator, id: number): Promise<void> {
    now = T0 + id * 60_000
    latest = frame({ id, ts: now })
    c.tick()
    await flush()
  }

  it('skips a busy assistant instead of queueing frames behind it', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)
    const release = a.hangUntilReleased()

    await offerFrame(c, 1)
    expect(a.analyzed).toHaveLength(1) // in flight, hanging

    await offerFrame(c, 2)
    expect(a.analyzed).toHaveLength(1) // skipped, NOT queued

    release()
    await flush()

    // Free again → the next frame is analyzed.
    await offerFrame(c, 3)
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

    await offerFrame(c, 1)
    await offerFrame(c, 2)

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

  it('reports a denied context switch WITHOUT its title, and never its pixels', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    now = T0 + 3_000
    latest = frame({ id: 2, ts: now, app: 'Google Chrome', windowTitle: 'Chase — Log in' })
    c.tick()
    await flush()

    // The move to the bank IS a context switch (assistants must know the user
    // left Slack) — but the title is withheld, since an assistant would otherwise
    // be free to paste "Chase — Log in" into a cloud prompt. The departing frame
    // is the Slack one, and the bank frame is never analyzed.
    expect(a.switches).toHaveLength(1)
    expect(a.switches[0].departing?.app).toBe('Slack')
    expect(a.switches[0].title).toBeNull()
    expect(a.analyzed.map((f) => f.app)).toEqual(['Slack'])
  })
})

describe('distribution gate (the expensive one)', () => {
  it('does NOT analyze every new frame while the user types in one window', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    // Ten minutes of editing: capture writes a new row ~1s (the pHash keeps
    // moving as text appears), the coordinator ticks every 3s, and the context —
    // app + window title — never changes.
    for (let i = 0; i <= 200; i++) {
      now = T0 + i * 3_000
      latest = frame({ id: i + 1, ts: now })
      c.tick()
      await flush() // let analyze() settle, so backpressure isn't what's skipping
    }

    // 201 distinct frames, but only the first + one per 60s fallback. Ungated,
    // this would be 201 screenshots on their way to a cloud model.
    expect(a.analyzed).toHaveLength(11)
  })

  // A debounce that restarts on every frame would never fire. Titles that churn
  // in a way the normalizer doesn't strip (a live word count, an edit counter)
  // would otherwise silence the assistants for as long as the user keeps typing.
  it('still distributes on the fallback when the context changes on EVERY frame', async () => {
    const c = make()
    const a = new TestAssistant()
    a.needsDelayFrames = true // ignore the quiet window; the gate is what's under test
    c.register(a)

    for (let i = 0; i <= 40; i++) {
      now = T0 + i * 3_000
      latest = frame({ id: i + 1, ts: now, windowTitle: `notes — ${i} words` })
      c.tick()
      await flush()
    }

    // First frame, then one per 60s fallback (T0+60s, T0+120s) — not zero.
    expect(a.analyzed).toHaveLength(3)
  })

  it('debounces a context switch: one distribution of the LATEST frame, not one per hop', async () => {
    const c = make()
    const a = new TestAssistant()
    a.needsDelayFrames = true // see it despite the post-switch quiet window
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    // Three fast hops inside the 3s debounce → nothing distributed yet.
    for (let i = 1; i <= 3; i++) {
      now = T0 + i * 1_000
      latest = frame({ id: 1 + i, ts: now, app: `App${i}`, windowTitle: `w${i}` })
      c.tick()
    }
    await flush()
    expect(a.analyzed).toHaveLength(1) // still only the first frame

    // Settled: the next tick past the debounce flushes the LATEST frame only.
    now = T0 + 7_000
    latest = frame({ id: 9, ts: now, app: 'App3', windowTitle: 'w3' })
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(2)
    expect(a.analyzed[1].id).toBe(9)
  })

  it('uses the 15s messaging fallback so a reply landing in Slack is not missed', async () => {
    const c = make()
    const a = new TestAssistant()
    c.register(a)

    latest = frame({ id: 1, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    now = T0 + 15_000
    latest = frame({ id: 2, ts: now, app: 'Slack', windowTitle: 'general' })
    c.tick()
    await flush()

    expect(a.analyzed).toHaveLength(2) // a code editor would still be waiting
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

    // The debounce flush lands (T0+6s) but the quiet window swallows it...
    now = T0 + 6_000
    latest = frame({ id: 3, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1)

    // ...still quiet at 59s...
    now = T0 + 59_000
    latest = frame({ id: 4, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(1)

    // ...and analysis of the new context resumes once BOTH the quiet window and
    // the 60s distribution fallback (from the debounce flush) have elapsed.
    now = T0 + 66_000
    latest = frame({ id: 5, ts: now, app: 'Chrome', windowTitle: 'Docs' })
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
    c.tick() // switch → debounce
    await flush()

    now = T0 + 6_000
    latest = frame({ id: 3, ts: now, app: 'Chrome', windowTitle: 'Docs' })
    c.tick() // debounce flushes; the quiet window does not apply to this one
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

    // No switch → no quiet window, no debounce; the frame is simply skipped by
    // the fallback gate, exactly like any other unchanged context.
    expect(a.switches).toHaveLength(0)
    expect(a.analyzed).toHaveLength(1)

    now = T0 + 60_000
    latest = frame({ id: 3, ts: now, app: 'Terminal', windowTitle: '⠙ Building — 01:01' })
    c.tick()
    await flush()
    expect(a.analyzed).toHaveLength(2) // the 60s fallback, not a "switch"
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
