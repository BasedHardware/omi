import { describe, it, expect } from 'vitest'
import { AdtsFrameExtractor } from './adtsFrameExtractor'

/** Builds a syntactically valid ADTS frame of the given total length. */
const adtsFrame = (length: number, fill = 0xaa): Uint8Array => {
  const frame = new Uint8Array(length)
  frame[0] = 0xff
  frame[1] = 0xf1
  frame[2] = 0x50
  frame[3] = (length >> 11) & 0x03
  frame[4] = (length >> 3) & 0xff
  frame[5] = ((length & 0x07) << 5) | 0x1f
  frame.fill(fill, 6)
  return frame
}

describe('AdtsFrameExtractor', () => {
  it('drains every complete frame in one push', () => {
    const extractor = new AdtsFrameExtractor()
    const a = adtsFrame(20, 0x01)
    const b = adtsFrame(15, 0x02)
    const merged = new Uint8Array(35)
    merged.set(a, 0)
    merged.set(b, 20)
    const frames = extractor.push(merged)
    expect(frames.length).toBe(2)
    expect(frames[0]).toEqual(a)
    expect(frames[1]).toEqual(b)
    expect(extractor.bufferedByteCount).toBe(0)
  })

  it('buffers partial frames across pushes', () => {
    const extractor = new AdtsFrameExtractor()
    const frame = adtsFrame(30, 0x07)
    expect(extractor.push(frame.subarray(0, 12))).toEqual([])
    const frames = extractor.push(frame.subarray(12))
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })

  it('drops junk before the syncword one byte at a time', () => {
    const extractor = new AdtsFrameExtractor()
    const frame = adtsFrame(10, 0x03)
    const withJunk = new Uint8Array(4 + frame.length)
    withJunk.set([0x11, 0x22, 0x33, 0x44], 0)
    withJunk.set(frame, 4)
    const frames = extractor.push(withJunk)
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(frame)
  })

  it('advances past a false sync whose length field is under 7', () => {
    const extractor = new AdtsFrameExtractor()
    // A syncword whose 13-bit length decodes to 0 would loop forever if the
    // extractor did not advance.
    const falseSync = Uint8Array.from([0xff, 0xf1, 0x00, 0x00, 0x00, 0x00])
    const real = adtsFrame(12, 0x04)
    const merged = new Uint8Array(falseSync.length + real.length)
    merged.set(falseSync, 0)
    merged.set(real, falseSync.length)
    const frames = extractor.push(merged)
    expect(frames.length).toBe(1)
    expect(frames[0]).toEqual(real)
  })

  it('clear drops buffered bytes', () => {
    const extractor = new AdtsFrameExtractor()
    extractor.push(adtsFrame(40).subarray(0, 10))
    expect(extractor.bufferedByteCount).toBe(10)
    extractor.clear()
    expect(extractor.bufferedByteCount).toBe(0)
  })
})
