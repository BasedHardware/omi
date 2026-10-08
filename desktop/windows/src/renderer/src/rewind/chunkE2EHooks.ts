// E2E-only hooks for video chunks, installed ONLY when the app runs under the
// harness (OMI_E2E=1 → window.omi.isE2E). Same pattern as
// `capture/e2eHooks.ts`, and for the same reason: the interesting part here is
// the real WebCodecs encode/decode round trip, which cannot run under
// plain-node vitest, and the only honest way to test it is to run the
// PRODUCTION modules inside a real Electron renderer rather than a copy of them.
import { encodeFramesToChunk } from './chunkEncoder'
import { ChunkFrameReader } from './chunkDecoder'

/**
 * Draw a frame that looks like a screen, and JPEG-encode it exactly as capture
 * does (`RewindCaptureHost`'s `standard` tier: JPEG at quality 0.7).
 *
 * Text-heavy on purpose. A flat colour field is not a fair stand-in: it
 * compresses so well as a JPEG that the baseline the chunk is measured against
 * is unrealistically small, which understates the saving and makes the
 * assertion meaningless. Real screens are dense small text, which is precisely
 * what makes per-frame JPEGs expensive.
 *
 * Only one line changes per frame, mirroring the thing that makes compaction
 * pay: consecutive screen captures are nearly identical.
 */
async function makeFrame(width: number, height: number, index: number): Promise<Uint8Array> {
  const canvas = new OffscreenCanvas(width, height)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('no 2d context')
  ctx.fillStyle = '#101820'
  ctx.fillRect(0, 0, width, height)
  ctx.font = '13px monospace'
  const lineHeight = 17
  const rows = Math.floor(height / lineHeight)
  for (let row = 0; row < rows; row++) {
    // A deterministic pseudo-random line of code-like text, stable across
    // frames except for the one the caret is on.
    const seed = row * 2654435761
    ctx.fillStyle = row % 4 === 0 ? '#7fd1b9' : '#d8dee9'
    let line = ''
    for (let col = 0; col < 100; col++) {
      const n = (seed + col * 40503 + (row === index % rows ? index : 0)) >>> 0
      line += String.fromCharCode(33 + (n % 90))
    }
    ctx.fillText(line, 8, (row + 1) * lineHeight)
  }
  const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.7 })
  return new Uint8Array(await blob.arrayBuffer())
}

/** Mean absolute per-channel difference between two same-sized RGBA buffers. */
function meanAbsoluteDifference(a: Uint8ClampedArray, b: Uint8ClampedArray): number {
  let total = 0
  let n = 0
  for (let i = 0; i < a.length; i += 4) {
    for (let k = 0; k < 3; k++) {
      total += Math.abs(a[i + k] - b[i + k])
      n++
    }
  }
  return total / n
}

async function rgbaOf(
  bytes: Uint8Array,
  width: number,
  height: number
): Promise<Uint8ClampedArray> {
  const bitmap = await createImageBitmap(new Blob([bytes as BlobPart], { type: 'image/jpeg' }))
  const canvas = new OffscreenCanvas(width, height)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('no 2d context')
  ctx.drawImage(bitmap, 0, 0, width, height)
  bitmap.close()
  return ctx.getImageData(0, 0, width, height).data
}

export function installRewindChunkE2EHooks(): void {
  if (!window.omi?.isE2E) return
  ;(window as unknown as Record<string, unknown>).__omiRewindChunkE2E = {
    /**
     * The whole round trip through the production encoder, container and
     * decoder: N generated frames in, N frames back out, with the sizes and the
     * per-frame fidelity the harness asserts on.
     */
    roundTrip: async (
      count: number,
      width: number,
      height: number
    ): Promise<{
      jpegBytes: number
      chunkBytes: number
      framesBack: number
      maxMeanDiff: number
      firstTs: number
      lastTs: number
    }> => {
      const baseTs = 1_781_329_148_845
      const frames: { captureTsMs: number; jpeg: Uint8Array }[] = []
      for (let i = 0; i < count; i++) {
        frames.push({ captureTsMs: baseTs + i * 1000, jpeg: await makeFrame(width, height, i) })
      }
      const jpegBytes = frames.reduce((s, f) => s + f.jpeg.byteLength, 0)

      const chunk = await encodeFramesToChunk({ width, height, frames })

      // Read every frame back through the real cursor, in order — the same path
      // and the same object a scrub uses.
      const reader = new ChunkFrameReader()
      const load = async (): Promise<Uint8Array> => new Uint8Array(chunk)
      let framesBack = 0
      let maxMeanDiff = 0
      for (let i = 0; i < count; i++) {
        const blob = await reader.readFrame('2026-08-17/1-2.omichunk', i, load)
        const back = new Uint8Array(await blob.arrayBuffer())
        const [source, decoded] = await Promise.all([
          rgbaOf(frames[i].jpeg, width, height),
          rgbaOf(back, width, height)
        ])
        maxMeanDiff = Math.max(maxMeanDiff, meanAbsoluteDifference(source, decoded))
        framesBack++
      }
      reader.retire()

      return {
        jpegBytes,
        chunkBytes: chunk.byteLength,
        framesBack,
        maxMeanDiff,
        firstTs: frames[0].captureTsMs,
        lastTs: frames[count - 1].captureTsMs
      }
    },

    /** Whether this machine can encode at all, and with which codec. */
    codecFor: async (width: number, height: number): Promise<string | null> => {
      const { pickChunkCodec } = await import('./chunkEncoder')
      return pickChunkCodec(width, height)
    }
  }
}
