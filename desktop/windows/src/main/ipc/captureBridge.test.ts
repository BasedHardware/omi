import { describe, it, expect } from 'vitest'
import { routeCaptureEvent, isOwnedCaptureEvent } from './captureBridge'
import type { CaptureEvent } from '../../shared/types'

// The bridge's routing decision is pure: owned events (audio errors, PTT) go to
// the single UI window that issued the command; everything else broadcasts to
// every non-capture window. These tests pin that decision without Electron.

const owned: CaptureEvent[] = [
  { type: 'audio-source-error', sessionId: 's', name: 'NotAllowedError', message: 'x' },
  { type: 'ptt-chunk', captureId: 'c', pcm: new ArrayBuffer(4) },
  { type: 'ptt-drained', captureId: 'c', pcm: new ArrayBuffer(4) },
  { type: 'ptt-capped', captureId: 'c' },
  { type: 'ptt-error', captureId: 'c', message: 'x' },
  { type: 'ptt-levels', captureId: 'c', bins: [1, 2] }
]

const broadcast: CaptureEvent[] = [
  { type: 'live', op: { op: 'reset' } },
  { type: 'vad-status', mode: 'fallback', reason: 'x' },
  { type: 'capture-window-restarted' }
]

describe('isOwnedCaptureEvent', () => {
  it('classifies owned vs broadcast events', () => {
    for (const e of owned) expect(isOwnedCaptureEvent(e)).toBe(true)
    for (const e of broadcast) expect(isOwnedCaptureEvent(e)).toBe(false)
  })
})

describe('routeCaptureEvent', () => {
  it('routes an owned event to its owner only', () => {
    for (const e of owned) {
      expect(routeCaptureEvent(e, 2, [1, 2, 3])).toEqual([2])
    }
  })

  it('drops an owned event when its owner window is gone', () => {
    for (const e of owned) {
      expect(routeCaptureEvent(e, 9, [1, 2, 3])).toEqual([])
      expect(routeCaptureEvent(e, undefined, [1, 2, 3])).toEqual([])
    }
  })

  it('broadcasts non-owned events to every candidate window', () => {
    for (const e of broadcast) {
      expect(routeCaptureEvent(e, undefined, [1, 2, 3])).toEqual([1, 2, 3])
      // An ownerId on a broadcast event is ignored — it still fans out.
      expect(routeCaptureEvent(e, 2, [1, 2, 3])).toEqual([1, 2, 3])
    }
  })

  it('broadcasts to nobody when there are no candidate windows', () => {
    expect(routeCaptureEvent(broadcast[0], undefined, [])).toEqual([])
  })
})
