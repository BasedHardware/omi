import { NativeImage } from 'electron'

// Same perceptual-dedup scheme as RewindOCRService.swift: 9x8 grayscale dHash,
// Hamming distance <= 5 bits treated as "same screen".

export const DHASH_SAME_SCREEN_THRESHOLD = 5

export function dhash(image: NativeImage): bigint {
  const small = image.resize({ width: 9, height: 8, quality: 'good' })
  const bitmap = small.toBitmap() // BGRA
  const { width } = small.getSize()
  let hash = 0n
  let bit = 0n
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 8; x++) {
      const i = (y * width + x) * 4
      const j = (y * width + x + 1) * 4
      const left = bitmap[i] * 0.114 + bitmap[i + 1] * 0.587 + bitmap[i + 2] * 0.299
      const right = bitmap[j] * 0.114 + bitmap[j + 1] * 0.587 + bitmap[j + 2] * 0.299
      if (left > right) hash |= 1n << bit
      bit++
    }
  }
  return hash
}

export function hammingDistance(a: bigint, b: bigint): number {
  let x = a ^ b
  let count = 0
  while (x > 0n) {
    count += Number(x & 1n)
    x >>= 1n
  }
  return count
}
