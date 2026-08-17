import { describe, it, expect } from 'vitest'
import { STORED_CHUNK_SECONDS, StorageChunker, stampFrames } from './storageChunker'

const FPS = 50
const EPOCH = 1_723_800_000

const frames = (
  count: number,
  startEpoch: number,
  framesPerSecond = FPS
): Array<{
  bytes: Uint8Array
  epochSeconds: number
}> =>
  Array.from({ length: count }, (_v, i) => ({
    bytes: Uint8Array.from([i & 0xff]),
    epochSeconds: startEpoch + Math.floor(i / framesPerSecond)
  }))

describe('StorageChunker', () => {
  it('emits a chunk once it holds a full chunk of audio', () => {
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    const complete = chunker.push(frames(STORED_CHUNK_SECONDS * FPS, EPOCH))
    expect(complete.length).toBe(1)
    expect(complete[0].seconds).toBe(STORED_CHUNK_SECONDS)
    expect(complete[0].startEpochSeconds).toBe(EPOCH)
    expect(chunker.pendingFrameCount).toBe(0)
  })

  it('holds a partial chunk until flushed', () => {
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    expect(chunker.push(frames(10 * FPS, EPOCH))).toEqual([])
    const flushed = chunker.flush()
    expect(flushed.length).toBe(1)
    expect(flushed[0].seconds).toBe(10)
  })

  it('splits a long run into several chunks', () => {
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    const complete = chunker.push(frames(STORED_CHUNK_SECONDS * FPS * 2, EPOCH))
    expect(complete.length).toBe(2)
    // Each chunk carries its own capture start.
    expect(complete[1].startEpochSeconds).toBe(EPOCH + STORED_CHUNK_SECONDS)
  })

  it('starts a new chunk when the capture time jumps', () => {
    // Two runs recorded an hour apart are two recordings; merging them would
    // date most of the audio wrongly.
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    const first = frames(5 * FPS, EPOCH)
    const second = frames(5 * FPS, EPOCH + 3600)
    const complete = chunker.push([...first, ...second])
    expect(complete.length).toBe(1)
    expect(complete[0].startEpochSeconds).toBe(EPOCH)
    expect(chunker.flush()[0].startEpochSeconds).toBe(EPOCH + 3600)
  })

  it('starts a new chunk when the capture time goes backwards', () => {
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    const complete = chunker.push([...frames(2 * FPS, EPOCH), ...frames(2 * FPS, EPOCH - 500)])
    expect(complete.length).toBe(1)
    expect(chunker.flush().length).toBe(1)
  })

  it('does not split on the ordinary drift inside one recording', () => {
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    chunker.push(frames(30 * FPS, EPOCH))
    expect(chunker.pendingFrameCount).toBe(30 * FPS)
    expect(chunker.flush().length).toBe(1)
  })

  it('reports byte length and reset clears the buffer', () => {
    const chunker = new StorageChunker({ framesPerSecond: FPS })
    chunker.push(frames(100, EPOCH))
    chunker.reset()
    expect(chunker.pendingFrameCount).toBe(0)
    expect(chunker.flush()).toEqual([])
  })

  it('flushing an empty chunker yields nothing', () => {
    expect(new StorageChunker({ framesPerSecond: FPS }).flush()).toEqual([])
  })
})

describe('stampFrames', () => {
  it('spreads frames across seconds from the record time', () => {
    const stamped = stampFrames(
      Array.from({ length: 100 }, () => new Uint8Array(1)),
      EPOCH,
      [],
      FPS
    )
    expect(stamped[0].epochSeconds).toBe(EPOCH)
    expect(stamped[49].epochSeconds).toBe(EPOCH)
    expect(stamped[50].epochSeconds).toBe(EPOCH + 1)
    expect(stamped[99].epochSeconds).toBe(EPOCH + 1)
  })

  it('an embedded marker re-anchors the frames after it', () => {
    const stamped = stampFrames(
      Array.from({ length: 4 }, () => new Uint8Array(1)),
      EPOCH,
      [{ frameIndex: 2, epochSeconds: EPOCH + 900 }],
      FPS
    )
    expect(stamped.map((f) => f.epochSeconds)).toEqual([EPOCH, EPOCH, EPOCH + 900, EPOCH + 900])
  })

  it('handles several markers in order', () => {
    const stamped = stampFrames(
      Array.from({ length: 4 }, () => new Uint8Array(1)),
      EPOCH,
      [
        { frameIndex: 1, epochSeconds: EPOCH + 100 },
        { frameIndex: 3, epochSeconds: EPOCH + 200 }
      ],
      FPS
    )
    expect(stamped.map((f) => f.epochSeconds)).toEqual([
      EPOCH,
      EPOCH + 100,
      EPOCH + 100,
      EPOCH + 200
    ])
  })

  it('a marker at the first frame replaces the record time', () => {
    const stamped = stampFrames(
      [new Uint8Array(1)],
      EPOCH,
      [{ frameIndex: 0, epochSeconds: EPOCH + 42 }],
      FPS
    )
    expect(stamped[0].epochSeconds).toBe(EPOCH + 42)
  })
})
