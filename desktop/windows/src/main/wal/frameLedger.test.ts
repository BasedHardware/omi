import { describe, it, expect } from 'vitest'
import { WalFrameLedger, type CaptureFrame, type FrameDisposition } from './frameLedger'
import {
  WAL_CHUNK_SECONDS,
  WAL_LOSS_THRESHOLD_SECONDS,
  WAL_NEW_FRAME_SYNC_DELAY_SECONDS
} from '../../shared/wal'

const FRAME_MS = 250
const START = 1_723_800_000_000
/** Frames per second of audio at the harness frame size. */
const PER_SECOND = 1000 / FRAME_MS
/** A judged window: the unit the loss threshold is measured over. */
const WINDOW = WAL_CHUNK_SECONDS

/** A clock the test advances by hand. */
const clock = (): { now: () => number; advance: (ms: number) => void; at: () => number } => {
  let current = START
  return {
    now: () => current,
    advance: (ms) => {
      current += ms
    },
    at: () => current
  }
}

/** Feeds `seconds` of audio, advancing the clock as real capture would. */
const feed = (
  ledger: WalFrameLedger,
  c: ReturnType<typeof clock>,
  seconds: number,
  disposition: FrameDisposition
): void => {
  const count = Math.round(seconds * PER_SECOND)
  for (let i = 0; i < count; i += 1) {
    const frame: CaptureFrame = {
      // 16 kHz mono s16 is 32 bytes per millisecond.
      bytes: new Uint8Array(FRAME_MS * 32),
      capturedAtMs: c.at(),
      durationMs: FRAME_MS,
      disposition
    }
    ledger.push(frame)
    c.advance(FRAME_MS)
  }
}

/** Lets the judging delay elapse so fed audio becomes judgeable. */
const settle = (c: ReturnType<typeof clock>): void => {
  c.advance(WAL_NEW_FRAME_SYNC_DELAY_SECONDS * 1000 + 1000)
}

describe('WalFrameLedger judging delay', () => {
  it('leaves recent audio alone so a connecting socket can still take it', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW, 'missed')
    // The tail of what was just fed is still inside the delay, so the window is
    // not yet complete and nothing is judged.
    expect(ledger.chunk()).toEqual([])
    expect(ledger.bufferedFrameCount).toBeGreaterThan(0)

    settle(c)
    const chunks = ledger.chunk()
    expect(chunks.length).toBe(1)
    expect(chunks[0].seconds).toBe(WINDOW)
  })

  it('never judges a frame that is still buffered for a connecting socket', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, 4, 'missed')
    feed(ledger, c, 2, 'buffered')
    feed(ledger, c, WINDOW * 2, 'missed')
    settle(c)

    // Judging stops at the buffered run, and the 6 s ahead of it is not a full
    // window, so nothing is emitted while that audio may still be in flight.
    expect(ledger.chunk()).toEqual([])
    expect(ledger.bufferedFrameCount).toBeGreaterThan(WINDOW * 2 * PER_SECOND)
  })

  it('resolves buffered frames when the socket flushes them', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW, 'buffered')
    expect(ledger.resolveBuffered('sent')).toBe(WINDOW * PER_SECOND)
    settle(c)
    // The socket took all of it, so there is nothing to store.
    expect(ledger.chunk()).toEqual([])
  })

  it('resolves only the flushed prefix when the buffer was partly dropped', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW, 'buffered')
    ledger.resolveBuffered('sent', 20 * PER_SECOND)
    ledger.resolveBuffered('missed')
    settle(c)

    const chunks = ledger.chunk()
    expect(chunks.length).toBe(1)
    // The leading run the socket took is recorded so the upload knows what was
    // already transcribed live.
    expect(chunks[0].syncedFrameOffset).toBe(20 * PER_SECOND)
    expect(chunks[0].fullySynced).toBe(false)
  })
})

describe('WalFrameLedger synced prefix', () => {
  it('counts only the leading run the socket took, not every sent frame', () => {
    // Audio that arrives AFTER a gap cannot extend the prefix: the upload skips
    // a prefix, so counting later sent frames would skip audio that was never
    // transcribed and silently lose it.
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, 5, 'sent')
    feed(ledger, c, WAL_LOSS_THRESHOLD_SECONDS, 'missed')
    feed(ledger, c, WINDOW - 5 - WAL_LOSS_THRESHOLD_SECONDS, 'sent')
    settle(c)

    const [chunk] = ledger.chunk()
    expect(chunk.syncedFrameOffset).toBe(5 * PER_SECOND)
    expect(chunk.totalFrames).toBe(WINDOW * PER_SECOND)
    expect(chunk.fullySynced).toBe(false)
  })

  it('a fully taken window has a prefix covering all of it', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now, storeEverything: true })
    feed(ledger, c, WINDOW, 'sent')
    settle(c)
    const [chunk] = ledger.chunk()
    expect(chunk.syncedFrameOffset).toBe(chunk.totalFrames)
    expect(chunk.fullySynced).toBe(true)
  })
})

describe('WalFrameLedger loss threshold', () => {
  it('ignores a short gap inside an otherwise healthy window', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, 10, 'sent')
    feed(ledger, c, WAL_LOSS_THRESHOLD_SECONDS - 1, 'missed')
    feed(ledger, c, WINDOW, 'sent')
    settle(c)
    // A couple of seconds lost around a reconnect is not a lost recording.
    expect(ledger.chunk()).toEqual([])
  })

  it('stores a window that lost enough audio to matter', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WAL_LOSS_THRESHOLD_SECONDS, 'missed')
    feed(ledger, c, WINDOW, 'sent')
    settle(c)
    const chunks = ledger.chunk()
    expect(chunks.length).toBe(1)
    expect(chunks[0].fullySynced).toBe(false)
  })

  it('measures the threshold per window, so a long outage is never sliced away', () => {
    // The judged span here is far longer than one window; if the threshold were
    // applied to whatever happened to be judgeable, frequent polling would
    // discard the outage a slice at a time.
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW * 3, 'missed')
    settle(c)
    let total = 0
    // Poll repeatedly, as a scheduler would.
    for (let i = 0; i < 5; i += 1) total += ledger.chunk().length
    expect(total).toBe(3)
  })

  it('stores everything when the unlimited-storage preference is on', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now, storeEverything: true })
    feed(ledger, c, WINDOW, 'sent')
    settle(c)
    const chunks = ledger.chunk()
    expect(chunks.length).toBe(1)
    expect(chunks[0].fullySynced).toBe(true)
  })
})

describe('WalFrameLedger chunk shape', () => {
  it('stamps the capture start in unix seconds and reports duration', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW, 'missed')
    settle(c)
    const [chunk] = ledger.chunk()
    expect(chunk.timerStart).toBe(Math.floor(START / 1000))
    expect(chunk.seconds).toBe(WINDOW)
    expect(chunk.totalFrames).toBe(WINDOW * PER_SECOND)
    expect(chunk.byteLength).toBe(WINDOW * PER_SECOND * FRAME_MS * 32)
  })

  it('splits a long outage into window-sized files, keeping the remainder', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW * 2.5, 'missed')
    settle(c)
    const chunks = ledger.chunk()
    // One unbounded upload would be a single huge file and a single failure.
    expect(chunks.length).toBe(2)
    expect(chunks[0].seconds).toBe(WINDOW)
    // Each file carries its own capture time.
    expect(chunks[1].timerStart).toBe(chunks[0].timerStart + WINDOW)
    // The partial window waits for more audio rather than being judged early.
    expect(ledger.bufferedFrameCount).toBe(WINDOW * 0.5 * PER_SECOND)

    const drained = ledger.drain()
    expect(drained.length).toBe(1)
    expect(drained[0].seconds).toBe(WINDOW / 2)
  })

  it('consumed frames leave the buffer', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW, 'missed')
    settle(c)
    ledger.chunk()
    expect(ledger.bufferedFrameCount).toBe(0)
    expect(ledger.chunk()).toEqual([])
  })
})

describe('WalFrameLedger memory bound', () => {
  it('judges the oldest audio once the buffer passes the cap', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now, maxBufferedMs: 20_000 })
    // Every frame is inside the delay window, so without the cap none of this
    // would ever be judged and the buffer would grow for the whole outage.
    feed(ledger, c, WINDOW * 2, 'missed')
    c.advance(-WINDOW * 2 * 1000)
    const chunks = ledger.chunk()
    expect(chunks.length).toBe(2)
  })

  it('the cap still refuses to judge in-flight buffered audio', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now, maxBufferedMs: 1_000 })
    feed(ledger, c, WINDOW * 2, 'buffered')
    c.advance(-WINDOW * 2 * 1000)
    expect(ledger.chunk()).toEqual([])
  })
})

describe('WalFrameLedger drain', () => {
  it('emits pending audio at session end regardless of the delay or window size', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, 3, 'missed')
    // Under both the delay and the window, so chunk() stores nothing.
    expect(ledger.chunk()).toEqual([])
    const drained = ledger.drain()
    expect(drained.length).toBe(1)
    expect(drained[0].seconds).toBe(3)
    expect(ledger.bufferedFrameCount).toBe(0)
  })

  it('drops audio the socket fully took', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, 10, 'sent')
    expect(ledger.drain()).toEqual([])
  })

  it('reset discards the buffer without emitting', () => {
    const c = clock()
    const ledger = new WalFrameLedger({ now: c.now })
    feed(ledger, c, WINDOW, 'missed')
    ledger.reset()
    expect(ledger.bufferedFrameCount).toBe(0)
    expect(ledger.drain()).toEqual([])
  })
})
