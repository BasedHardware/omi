import { describe, it, expect } from 'vitest'
import { FixedSizeRechunker } from './fixedSizeRechunker'

describe('FixedSizeRechunker', () => {
  it('emits exact chunks and buffers the remainder', () => {
    const rechunker = new FixedSizeRechunker(80)
    const first = rechunker.push(new Uint8Array(100).fill(1))
    expect(first.length).toBe(1)
    expect(first[0].length).toBe(80)
    const second = rechunker.push(new Uint8Array(60).fill(2))
    expect(second.length).toBe(1)
    expect(second[0].length).toBe(80)
    expect(Array.from(second[0].subarray(0, 20))).toEqual(new Array(20).fill(1))
    expect(Array.from(second[0].subarray(20))).toEqual(new Array(60).fill(2))
  })

  it('flush returns the trailing partial exactly once', () => {
    const rechunker = new FixedSizeRechunker(80)
    rechunker.push(new Uint8Array(100).fill(3))
    const tail = rechunker.flush()
    expect(tail).not.toBeNull()
    expect(tail!.length).toBe(20)
    expect(rechunker.flush()).toBeNull()
  })

  it('a single push can emit multiple chunks', () => {
    const rechunker = new FixedSizeRechunker(80)
    const chunks = rechunker.push(new Uint8Array(250))
    expect(chunks.length).toBe(3)
    expect(rechunker.flush()!.length).toBe(10)
  })
})
