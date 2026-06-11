import { describe, it, expect } from 'vitest'
import { averageHash, hammingDistance } from './frameHash'

// A 2x2 "bitmap" in Electron BGRA order (4 bytes/pixel).
// Pixel luminance ~ (r+g+b)/3; build dark vs light pixels.
const px = (v: number): number[] => [v, v, v, 255] // B,G,R,A
function bitmap(vals: number[]): Buffer {
  return Buffer.from(vals.flatMap(px))
}

describe('averageHash', () => {
  it('produces a bit per pixel: 1 when above the frame average', () => {
    // values 0,0,255,255 -> average 127.5 -> bits 0,0,1,1
    expect(averageHash(bitmap([0, 0, 255, 255]), 4)).toBe('0011')
  })
  it('is stable for identical input', () => {
    const b = bitmap([10, 200, 30, 240])
    expect(averageHash(b, 4)).toBe(averageHash(bitmap([10, 200, 30, 240]), 4))
  })
})

describe('hammingDistance', () => {
  it('counts differing bits', () => {
    expect(hammingDistance('0011', '0001')).toBe(1)
    expect(hammingDistance('0011', '0011')).toBe(0)
    expect(hammingDistance('1111', '0000')).toBe(4)
  })
  it('treats length mismatch as maximally different', () => {
    expect(hammingDistance('001', '0011')).toBe(Number.POSITIVE_INFINITY)
  })
})
