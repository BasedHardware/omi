// Average-hash (aHash) over a small BGRA bitmap (Electron NativeImage.toBitmap()).
// Pure: takes raw bytes + pixel count, returns a bit string. No image decoding here —
// the caller resizes the NativeImage to a tiny size first (e.g. 16x9 = 144 px).

/** @param bgra BGRA bytes, 4 per pixel. @param pixelCount number of pixels. */
export function averageHash(bgra: Buffer, pixelCount: number): string {
  const lum = new Array<number>(pixelCount)
  for (let i = 0; i < pixelCount; i++) {
    const o = i * 4
    lum[i] = (bgra[o] + bgra[o + 1] + bgra[o + 2]) / 3
  }
  const avg = lum.reduce((a, b) => a + b, 0) / pixelCount
  let bits = ''
  for (let i = 0; i < pixelCount; i++) bits += lum[i] > avg ? '1' : '0'
  return bits
}

/** Bit difference between two equal-length hash strings; Infinity if lengths differ. */
export function hammingDistance(a: string, b: string): number {
  if (a.length !== b.length) return Number.POSITIVE_INFINITY
  let d = 0
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d++
  return d
}
