import { describe, it, expect } from 'vitest'
import { routeCaptureEvent, isOwnedCaptureEvent } from './captureBridge'
import type { CaptureEvent } from '../../shared/types'

// The bridge's routing decision is pure: owned events (audio errors, PTT) go to
// the single UI window that issued the command; every other event through this
// path (live-store mirror, meeting-capture-status) is consumed only by the main
// window, so it targets the main window rather than fanning out to the
// bar/glow/toast windows that just drop it. These tests pin that decision without
// Electron.

const owned: CaptureEvent[] = [
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
  { type: 'meeting-capture-status', meetingId: 'm', status: 'started' },
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
