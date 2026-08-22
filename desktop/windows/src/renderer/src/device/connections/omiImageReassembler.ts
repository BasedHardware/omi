/**
 * Omi camera image reassembly — port of the chunk state machine in macOS
 * Connections/OmiDeviceConnection.swift. Chunks arrive as
 * [u16 frameIndex LE, ...payload]; 0xFFFF ends an image, 0 starts one, and
 * anything out of order discards the whole in-progress image.
 */

import { imageOrientationFromByte } from '../protocol/deviceTypes'
import type { OrientedImage } from './deviceConnection'

const END_MARKER = 0xffff
const BUFFER_CAP_BYTES = 200 * 1024
/** Firmware at or above this reports orientation in frame 0. */
const ORIENTATION_FIRMWARE_FLOOR = '2.1.1'

/** Numeric dotted comparison; missing parts count as 0. */
export const compareFirmwareVersions = (a: string, b: string): number => {
  const partsA = a.split('.').map((p) => Number.parseInt(p, 10) || 0)
  const partsB = b.split('.').map((p) => Number.parseInt(p, 10) || 0)
  const length = Math.max(partsA.length, partsB.length)
  for (let i = 0; i < length; i += 1) {
    const diff = (partsA[i] ?? 0) - (partsB[i] ?? 0)
    if (diff !== 0) return diff < 0 ? -1 : 1
  }
  return 0
}

export class OmiImageReassembler {
  private chunks: Uint8Array[] = []
  private bufferedBytes = 0
  private isTransferring = false
  private nextExpectedFrame = 0
  private orientationDegrees: OrientedImage['orientationDegrees'] = 0

  constructor(private readonly firmwareRevision: () => string) {}

  /** Feeds one notification chunk; returns a completed image or null. */
  push(chunk: Uint8Array): OrientedImage | null {
    if (chunk.length < 2) return null
    const frameIndex = chunk[0] | (chunk[1] << 8)

    if (frameIndex === END_MARKER) {
      let result: OrientedImage | null = null
      if (this.isTransferring && this.bufferedBytes > 0) {
        result = { imageData: this.concatenated(), orientationDegrees: this.orientationDegrees }
      }
      this.reset()
      return result
    }

    if (frameIndex === 0) {
      this.reset()
      this.isTransferring = true
    }

    if (!this.isTransferring) return null

    if (frameIndex !== this.nextExpectedFrame) {
      // Out-of-order frame: the whole in-progress image is unusable.
      this.reset()
      return null
    }

    let payload: Uint8Array
    if (frameIndex === 0) {
      const reportsOrientation =
        compareFirmwareVersions(this.firmwareRevision(), ORIENTATION_FIRMWARE_FLOOR) >= 0
      if (reportsOrientation && chunk.length > 2) {
        this.orientationDegrees = imageOrientationFromByte(chunk[2])
        payload = chunk.subarray(3)
      } else {
        // Older firmware sends images upside down and no orientation byte.
        this.orientationDegrees = 180
        payload = chunk.subarray(2)
      }
    } else {
      payload = chunk.subarray(2)
    }

    this.chunks.push(payload)
    this.bufferedBytes += payload.length
    this.nextExpectedFrame += 1

    if (this.bufferedBytes > BUFFER_CAP_BYTES) {
      this.reset()
    }
    return null
  }

  private concatenated(): Uint8Array {
    const out = new Uint8Array(this.bufferedBytes)
    let offset = 0
    for (const chunk of this.chunks) {
      out.set(chunk, offset)
      offset += chunk.length
    }
    return out
  }

  private reset(): void {
    this.chunks = []
    this.bufferedBytes = 0
    this.isTransferring = false
    this.nextExpectedFrame = 0
    this.orientationDegrees = 0
  }
}
