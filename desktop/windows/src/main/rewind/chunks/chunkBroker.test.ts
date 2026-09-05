// The encode channel's protocol: what happens when the renderer is slow,
// silent, duplicated, or gone. None of it needs Electron or a codec.
import { describe, expect, it, vi } from 'vitest'
import { ChunkEncodeBroker, pickEncodeTarget, type EncodeRequest } from './chunkBroker'

function broker(timeoutMs = 1000) {
  const sent: EncodeRequest[] = []
  const b = new ChunkEncodeBroker((r) => sent.push(r), timeoutMs)
  return { b, sent }
}

const input = { width: 1280, height: 720, frames: [{ captureTsMs: 1, jpeg: new Uint8Array([1]) }] }

describe('a normal encode', () => {
  it('sends the request and resolves with the bytes', async () => {
    const { b, sent } = broker()
    const promise = b.encode(input)
    expect(sent).toHaveLength(1)
    b.settle({ requestId: sent[0].requestId, ok: true, bytes: new Uint8Array([9, 9]) })
    expect([...(await promise)]).toEqual([9, 9])
  })

  it('gives every request its own id', async () => {
    const { b, sent } = broker()
    const a = b.encode(input)
    const c = b.encode(input)
    expect(sent[0].requestId).not.toBe(sent[1].requestId)
    b.settle({ requestId: sent[0].requestId, ok: true, bytes: new Uint8Array([1]) })
    b.settle({ requestId: sent[1].requestId, ok: true, bytes: new Uint8Array([2]) })
    expect([...(await a)]).toEqual([1])
    expect([...(await c)]).toEqual([2])
  })

  it('stops tracking a settled request', async () => {
    const { b, sent } = broker()
    const promise = b.encode(input)
    expect(b.inFlight).toBe(1)
    b.settle({ requestId: sent[0].requestId, ok: true, bytes: new Uint8Array([1]) })
    await promise
    expect(b.inFlight).toBe(0)
  })
})

describe('when the renderer does not cooperate', () => {
  it('rejects with the renderer’s error', async () => {
    const { b, sent } = broker()
    const promise = b.encode(input)
    b.settle({ requestId: sent[0].requestId, ok: false, error: 'no encoder available' })
    await expect(promise).rejects.toThrow('no encoder available')
  })

  it('times out rather than hanging forever', async () => {
    vi.useFakeTimers()
    try {
      const { b } = broker(500)
      const promise = b.encode(input)
      const assertion = expect(promise).rejects.toThrow(/timed out after 500ms/)
      await vi.advanceTimersByTimeAsync(500)
      await assertion
      expect(b.inFlight).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('ignores an answer that arrives after the timeout', async () => {
    // Late answers are normal, not exceptional: the encode really was still
    // running. Raising here would surface as an unhandled error in an IPC
    // handler for a request nobody is waiting on any more.
    vi.useFakeTimers()
    try {
      const { b, sent } = broker(500)
      const promise = b.encode(input)
      const assertion = expect(promise).rejects.toThrow(/timed out/)
      await vi.advanceTimersByTimeAsync(500)
      await assertion
      expect(() =>
        b.settle({ requestId: sent[0].requestId, ok: true, bytes: new Uint8Array([1]) })
      ).not.toThrow()
    } finally {
      vi.useRealTimers()
    }
  })

  it('ignores a duplicate answer', async () => {
    const { b, sent } = broker()
    const promise = b.encode(input)
    b.settle({ requestId: sent[0].requestId, ok: true, bytes: new Uint8Array([1]) })
    await promise
    expect(() =>
      b.settle({ requestId: sent[0].requestId, ok: true, bytes: new Uint8Array([2]) })
    ).not.toThrow()
  })

  it('ignores an answer for a request it never made', () => {
    const { b } = broker()
    expect(() => b.settle({ requestId: 'nope', ok: true, bytes: new Uint8Array() })).not.toThrow()
  })

  it('rejects when the request cannot even be sent', async () => {
    const b = new ChunkEncodeBroker(() => {
      throw new Error('window is gone')
    })
    await expect(b.encode(input)).rejects.toThrow('window is gone')
    expect(b.inFlight).toBe(0)
  })
})

describe('when the renderer goes away', () => {
  it('fails everything in flight instead of waiting out the timeout', async () => {
    // A pass sitting on an unresolvable promise holds its plan and every loaded
    // JPEG in memory for the whole timeout.
    const { b } = broker(60_000)
    const a = b.encode(input)
    const c = b.encode(input)
    b.abortAll('the encoding window closed')
    await expect(a).rejects.toThrow('the encoding window closed')
    await expect(c).rejects.toThrow('the encoding window closed')
    expect(b.inFlight).toBe(0)
  })

  it('is a no-op when nothing is in flight', () => {
    const { b } = broker()
    expect(() => b.abortAll('closed')).not.toThrow()
  })
})

describe('choosing a renderer', () => {
  const contents = (destroyed: boolean, crashed = false) =>
    ({ isDestroyed: () => destroyed, isCrashed: () => crashed }) as unknown as Parameters<
      typeof pickEncodeTarget
    >[0][number]

  it('takes the first live window', () => {
    const live = contents(false)
    expect(pickEncodeTarget([contents(true), live])).toBe(live)
  })

  it('skips a crashed renderer', () => {
    const live = contents(false)
    expect(pickEncodeTarget([contents(false, true), live])).toBe(live)
  })

  it('returns null when there is no window', () => {
    // A real state — the app can run with every window closed, and compaction
    // simply does not happen that pass.
    expect(pickEncodeTarget([])).toBeNull()
    expect(pickEncodeTarget([contents(true)])).toBeNull()
  })
})
