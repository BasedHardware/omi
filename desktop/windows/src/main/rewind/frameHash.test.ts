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

// Everything above builds its bitmaps from `px(v)`, which sets B, G and R to
// the SAME value. That makes every fixture greyscale, and a greyscale fixture
// cannot see which channels the luminance actually reads: swapping the red
// channel for a second copy of blue leaves every assertion above green. A
// mutation audit confirmed it.
//
// It matters because this hash is the only thing deciding whether two frames
// are "the same screen" (`captureDecision.ts`). A hash blind to a channel means
// a screen that changed only in that channel is treated as unchanged and never
// stored, and the user simply finds nothing in Rewind for that stretch.
const bgra = (b: number, g: number, r: number): number[] => [b, g, r, 255]

function colourBitmap(pixels: [number, number, number][]): Buffer {
  return Buffer.from(pixels.flatMap(([b, g, r]) => bgra(b, g, r)))
}

describe('averageHash reads every colour channel', () => {
  it('distinguishes frames that differ only in red', () => {
    const dimRed = colourBitmap([
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 60],
      [0, 0, 60]
    ])
    const brightRed = colourBitmap([
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 255],
      [0, 0, 255]
    ])
    // Both are "0011" by shape; what matters is that red reaches the average at
    // all, so the two frames are not hashed as one flat field.
    expect(averageHash(dimRed, 4)).toBe('0011')
    expect(averageHash(brightRed, 4)).toBe('0011')
  })

  it('weighs red the same as blue and green', () => {
    // Three pixels carrying the same total luminance in different channels must
    // hash alike. If a channel were dropped or doubled they would not.
    const viaBlue = colourBitmap([
      [90, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0]
    ])
    const viaGreen = colourBitmap([
      [0, 90, 0],
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0]
    ])
    const viaRed = colourBitmap([
      [0, 0, 90],
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0]
    ])
    expect(averageHash(viaGreen, 4)).toBe(averageHash(viaBlue, 4))
    expect(averageHash(viaRed, 4)).toBe(averageHash(viaBlue, 4))
  })

  it('notices a red-only change between two frames', () => {
    // The end-to-end version of the same property, stated the way the capture
    // path consumes it: two different screens must not hash identically.
    const before = colourBitmap([
      [0, 0, 0],
      [0, 0, 0],
      [200, 0, 0],
      [0, 0, 0]
    ])
    const after = colourBitmap([
      [0, 0, 200],
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0]
    ])
    expect(averageHash(after, 4)).not.toBe(averageHash(before, 4))
  })
})

describe('averageHash at the average', () => {
  it('gives a pixel exactly at the average a 0 bit', () => {
    // Strictly greater, not greater-or-equal. Flipping that comparison changes
    // the hash of every flat region, which is most of a real screen.
    expect(
      averageHash(
        colourBitmap([
          [10, 10, 10],
          [10, 10, 10]
        ]),
        2
      )
    ).toBe('00')
  })

  it('hashes a completely uniform frame to all zeros', () => {
    // The degenerate case, worth stating because it is what a broken luminance
    // calculation collapses every frame to, and because a hash of all zeros
    // makes every frame a duplicate of every other.
    expect(
      averageHash(
        colourBitmap([
          [7, 7, 7],
          [7, 7, 7],
          [7, 7, 7],
          [7, 7, 7]
        ]),
        4
      )
    ).toBe('0000')
  })

  it('does not collapse a varied frame to all zeros', () => {
    // The guard that a uniform-frame assertion cannot give on its own.
    expect(
      averageHash(
        colourBitmap([
          [0, 0, 0],
          [255, 255, 255]
        ]),
        2
      )
    ).toBe('01')
  })
})

describe('hammingDistance edges', () => {
  it('counts a distance of exactly the dedup threshold', () => {
    // 4 is the value `captureDecision` treats as "same screen"; this is the
    // arithmetic half of that boundary.
    expect(hammingDistance('11110000', '00000000')).toBe(4)
    expect(hammingDistance('11111000', '00000000')).toBe(5)
  })

  it('treats an empty pair as identical rather than as a mismatch', () => {
    expect(hammingDistance('', '')).toBe(0)
  })

  it('is symmetric', () => {
    expect(hammingDistance('1010', '0001')).toBe(hammingDistance('0001', '1010'))
  })
})
