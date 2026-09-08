import { describe, it, expect, vi } from 'vitest'
import {
  canForwardRendererCaptureCommand,
  emitCaptureEventFromMain,
  isOwnedCaptureEvent,
  onCaptureEventInMain,
  routeCaptureEvent
} from './captureBridge'
import type { CaptureEvent } from '../../shared/types'

vi.mock('electron', () => ({
  ipcMain: { on: vi.fn() },
  BrowserWindow: { getAllWindows: vi.fn(() => []) }
}))

// The bridge's routing decision is pure: owned events (audio readiness/errors, PTT) go to
// the single window that issued the command; every other event through this
// path (live-store mirror, meeting-capture-status) is consumed only by the main
// window, so it targets the main window rather than fanning out to the
// bar/glow/toast windows that just drop it. These tests pin that decision without
// Electron.

const owned: CaptureEvent[] = [
  { type: 'audio-source-ready', sessionId: 's' },
  { type: 'audio-source-error', sessionId: 's', name: 'NotAllowedError', message: 'x' },
  { type: 'ptt-chunk', captureId: 'c', pcm: new ArrayBuffer(4) },
  { type: 'ptt-drained', captureId: 'c', pcm: new ArrayBuffer(4) },
  { type: 'ptt-capped', captureId: 'c' },
  { type: 'ptt-error', captureId: 'c', message: 'x' },
  { type: 'ptt-levels', captureId: 'c', bins: [1, 2] }
]

// Non-owned events that flow through routeCaptureEvent in production.
// (capture-window-restarted is non-owned too, but never reaches this path — it
// originates in main via emitCaptureEventFromMain — so it isn't exercised here.)
const mainWindowOnly: CaptureEvent[] = [
  { type: 'live', op: { op: 'reset' } },
  { type: 'meeting-capture-status', meetingId: 'm', attemptId: 1, status: 'started' },
  { type: 'capture-window-restarted' }
]

describe('isOwnedCaptureEvent', () => {
  it('classifies owned vs non-owned events', () => {
    for (const e of owned) expect(isOwnedCaptureEvent(e)).toBe(true)
    for (const e of mainWindowOnly) expect(isOwnedCaptureEvent(e)).toBe(false)
  })
})

describe('routeCaptureEvent', () => {
  it('routes an owned event to its owner only', () => {
    for (const e of owned) {
      // main window id present but irrelevant for owned events.
      expect(routeCaptureEvent(e, 2, [1, 2, 3], 1)).toEqual([2])
    }
  })

  it('routes an owned event back to the capture window when it is the owner', () => {
    const captureWindowId = 4
    expect(routeCaptureEvent(owned[0], captureWindowId, [1, 2, captureWindowId], 1)).toEqual([
      captureWindowId
    ])
  })

  it('drops an owned event when its owner window is gone', () => {
    for (const e of owned) {
      expect(routeCaptureEvent(e, 9, [1, 2, 3], 1)).toEqual([])
      expect(routeCaptureEvent(e, undefined, [1, 2, 3], 1)).toEqual([])
    }
  })

  it('routes a non-owned event to the main window only', () => {
    for (const e of mainWindowOnly) {
      expect(routeCaptureEvent(e, undefined, [1, 2, 3], 1)).toEqual([1])
      // An ownerId on a non-owned event is ignored — it still goes to main only.
      expect(routeCaptureEvent(e, 2, [1, 2, 3], 1)).toEqual([1])
    }
  })

  it('drops a non-owned event when the main window is gone or unknown', () => {
    // main window not among the candidates (e.g. destroyed) → dropped, not fanned out.
    expect(routeCaptureEvent(mainWindowOnly[0], undefined, [2, 3], 1)).toEqual([])
    expect(routeCaptureEvent(mainWindowOnly[0], undefined, [1, 2, 3], undefined)).toEqual([])
  })

  it('routes to nobody when there are no candidate windows', () => {
    expect(routeCaptureEvent(mainWindowOnly[0], undefined, [], 1)).toEqual([])
  })
})

describe('emitCaptureEventFromMain', () => {
  it('notifies main-process listeners as well as renderer windows', () => {
    const seen: CaptureEvent[] = []
    const off = onCaptureEventInMain((event) => seen.push(event))
    const event: CaptureEvent = { type: 'capture-window-restarted' }

    emitCaptureEventFromMain(event, null)

    expect(seen).toEqual([event])
    off()
  })
})

describe('canForwardRendererCaptureCommand', () => {
  const owns = (sessionId: string, ownerId: number): boolean =>
    sessionId === 'owned' && ownerId === 7

  it('rejects renderer attempts to invoke main-only meeting capture', () => {
    expect(
      canForwardRendererCaptureCommand(
        {
          type: 'meeting-capture-start',
          meetingId: 'meeting-1',
          attemptId: 1,
          appName: 'Meet'
        },
        7,
        owns
      )
    ).toBe(false)
  })

  it('binds audio commands to a listen session owned by the sender', () => {
    expect(
      canForwardRendererCaptureCommand(
        { type: 'audio-start', sessionId: 'owned', source: 'mic' },
        7,
        owns
      )
    ).toBe(true)
    expect(
      canForwardRendererCaptureCommand(
        { type: 'audio-start', sessionId: 'other', source: 'mic' },
        7,
        owns
      )
    ).toBe(false)
    expect(
      canForwardRendererCaptureCommand({ type: 'audio-stop', sessionId: 'owned' }, 9, owns)
    ).toBe(false)
  })

  it('allows main-only UI controls (live-view etc.) only from the main window', () => {
    expect(canForwardRendererCaptureCommand({ type: 'live-view', active: true }, 7, owns, 7)).toBe(
      true
    )
    expect(canForwardRendererCaptureCommand({ type: 'live-view', active: true }, 8, owns, 7)).toBe(
      false
    )
  })

  it('allows PTT controls from either the main window or the bar (usePushToTalk is bar-only)', () => {
    expect(canForwardRendererCaptureCommand({ type: 'ptt-warm' }, 7, owns, 7, 42)).toBe(true) // main
    expect(canForwardRendererCaptureCommand({ type: 'ptt-warm' }, 42, owns, 7, 42)).toBe(true) // bar
    expect(canForwardRendererCaptureCommand({ type: 'ptt-warm' }, 8, owns, 7, 42)).toBe(false) // neither
  })

  it('does NOT extend the bar-window allowance to the main-only controls', () => {
    // The bar is the sole PTT sender, but must not gain live-view/screen-view/etc.
    expect(
      canForwardRendererCaptureCommand({ type: 'live-view', active: true }, 42, owns, 7, 42)
    ).toBe(false)
  })

  it('rejects unknown runtime commands instead of forwarding them', () => {
    expect(
      canForwardRendererCaptureCommand(
        { type: 'not-a-capture-command' } as unknown as Parameters<
          typeof canForwardRendererCaptureCommand
        >[0],
        7,
        owns,
        7
      )
    ).toBe(false)
  })
})
