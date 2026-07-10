import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { startPttCapture } from './capture'
import { DRAIN_MS } from './constants'
import type { CaptureCommand, CaptureEvent } from '../../../../shared/types'

// lib/ptt/capture.ts is now an IPC client: it drives the capture window over the
// bridge and reassembles chunks/levels/drain into the same PttCapture surface the
// hook depends on. These cover chunk ordering, the WaveformSource adapter, and
// drain resolve/timeout — without a real mic graph.

let commands: CaptureCommand[]
let evHandlers: Array<(e: CaptureEvent) => void>

function emit(e: CaptureEvent): void {
  for (const fn of [...evHandlers]) fn(e)
}
function lastStartId(): string {
  const start = commands.find((c) => c.type === 'ptt-start') as Extract<
    CaptureCommand,
    { type: 'ptt-start' }
  >
  return start.captureId
}
function i16buf(values: number[]): ArrayBuffer {
  return new Int16Array(values).buffer
}

beforeEach(() => {
  commands = []
  evHandlers = []
  ;(globalThis as Record<string, unknown>).window = {
    omi: {
      captureCommand: (c: CaptureCommand) => commands.push(c),
      onCaptureEvent: (fn: (e: CaptureEvent) => void) => {
        evHandlers.push(fn)
        return () => (evHandlers = evHandlers.filter((x) => x !== fn))
      }
    }
  }
})

describe('startPttCapture (IPC client)', () => {
  it('sends ptt-start and resolves once the first event arrives', async () => {
    const p = startPttCapture({ backfillMs: 42 })
    const start = commands.find((c) => c.type === 'ptt-start')
    expect(start).toMatchObject({ type: 'ptt-start', backfillMs: 42 })
    emit({ type: 'ptt-chunk', captureId: lastStartId(), pcm: i16buf([1]) })
    await expect(p).resolves.toBeTruthy()
  })

  it('replays chunks to onChunk in order (backfill seed first)', async () => {
    const seen: number[][] = []
    const p = startPttCapture({ onChunk: (pcm) => seen.push(Array.from(pcm)) })
    const id = lastStartId()
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([1, 1]) }) // backfill seed
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([2, 2]) })
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([3, 3]) })
    await p
    expect(seen).toEqual([
      [1, 1],
      [2, 2],
      [3, 3]
    ])
  })

  it('ignores events for a different captureId', async () => {
    const seen: number[][] = []
    const p = startPttCapture({ onChunk: (pcm) => seen.push(Array.from(pcm)) })
    emit({ type: 'ptt-chunk', captureId: lastStartId(), pcm: i16buf([1]) })
    emit({ type: 'ptt-chunk', captureId: 'someone-else', pcm: i16buf([9]) })
    await p
    expect(seen).toEqual([[1]])
  })

  it('the analyser reads zeros before the first levels frame, then the last frame', async () => {
    const p = startPttCapture({})
    const id = lastStartId()
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([0]) }) // resolve without levels
    const capture = await p
    const dest = new Uint8Array(4)
    dest.fill(200)
    capture.analyser.getByteFrequencyData(dest)
    expect(Array.from(dest)).toEqual([0, 0, 0, 0]) // zeros before any frame
    emit({ type: 'ptt-levels', captureId: id, bins: [10, 20, 30] })
    capture.analyser.getByteFrequencyData(dest)
    expect(Array.from(dest)).toEqual([10, 20, 30, 0]) // last frame, zero-padded
  })

  it('forwards ptt-capped to onCapped', async () => {
    const onCapped = vi.fn()
    const p = startPttCapture({ onCapped })
    const id = lastStartId()
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([1]) })
    await p
    emit({ type: 'ptt-capped', captureId: id })
    expect(onCapped).toHaveBeenCalledTimes(1)
  })

  it('drain() sends ptt-drain and resolves with the drained buffer', async () => {
    const p = startPttCapture({})
    const id = lastStartId()
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([1]) })
    const capture = await p
    const drainP = capture.drain()
    expect(commands.some((c) => c.type === 'ptt-drain')).toBe(true)
    emit({ type: 'ptt-drained', captureId: id, pcm: i16buf([7, 8, 9]) })
    expect(Array.from(await drainP)).toEqual([7, 8, 9])
  })

  it('rejects the start on ptt-error before it is live', async () => {
    const p = startPttCapture({})
    emit({ type: 'ptt-error', captureId: lastStartId(), message: 'mic dead' })
    await expect(p).rejects.toThrow('mic dead')
  })

  it('dispose() sends ptt-dispose', async () => {
    const p = startPttCapture({})
    const id = lastStartId()
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([1]) })
    const capture = await p
    capture.dispose()
    expect(commands.some((c) => c.type === 'ptt-dispose' && c.captureId === id)).toBe(true)
  })
})

describe('startPttCapture drain timeout', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('resolves empty if the capture window never replies', async () => {
    const p = startPttCapture({})
    const id = lastStartId()
    emit({ type: 'ptt-chunk', captureId: id, pcm: i16buf([1]) })
    const capture = await p
    const drainP = capture.drain()
    vi.advanceTimersByTime(2 * DRAIN_MS + 1)
    expect(Array.from(await drainP)).toEqual([])
  })
})
