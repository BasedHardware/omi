/**
 * Audio codec decoders — Windows port of macOS Audio/AudioCodecDecoder.swift.
 * Every decoder outputs 16 kHz mono signed 16-bit PCM, which is what the
 * transcription socket expects; BLE audio is never forwarded in its wire
 * codec.
 */

import type { BleAudioCodec } from '../protocol/deviceTypes'

export interface AudioDecoderSinks {
  /** Receives PCM produced outside a decode() return (async decoders). */
  onPcm: (pcm: Int16Array) => void
  /** Reports a decode failure produced outside decode() (async decoders). */
  onError: (error: Error) => void
}

export interface AudioDecoder {
  readonly codec: BleAudioCodec
  /** False for codecs decoded by a placeholder (LC3 silence). */
  readonly hasFullSupport: boolean
  /** True when PCM arrives through the sink rather than decode()'s return. */
  readonly isAsync: boolean
  /** Resolves when the decoder can accept frames. */
  readonly ready: Promise<void>
  /** Returns PCM for synchronous decoders, null for async ones (and on a
   *  failure the caller counts through the degradation ladder). */
  decode(frame: Uint8Array): Int16Array | null
  reset(): void
  close(): void
}

/** Opus packets whose first byte is outside this set are logged as suspect;
 *  the decode is still attempted, exactly as on macOS. */
export const VALID_OPUS_TOC_BYTES: ReadonlySet<number> = new Set([
  0x78, 0xb8, 0xf8, 0x70, 0xb0, 0xf0
])

const RESOLVED: Promise<void> = Promise.resolve()

// --- PCM --------------------------------------------------------------------

export class PcmDecoder implements AudioDecoder {
  readonly hasFullSupport = true
  readonly isAsync = false
  readonly ready = RESOLVED

  constructor(readonly codec: BleAudioCodec) {}

  decode(frame: Uint8Array): Int16Array | null {
    if (this.codec === 'pcm8') {
      // Unsigned 8-bit samples centered on 128.
      const out = new Int16Array(frame.length)
      for (let i = 0; i < frame.length; i += 1) {
        out[i] = (frame[i] - 128) * 256
      }
      return out
    }
    const sampleCount = frame.length >> 1
    const out = new Int16Array(sampleCount)
    for (let i = 0; i < sampleCount; i += 1) {
      const lo = frame[i * 2]
      const hi = frame[i * 2 + 1]
      const value = lo | (hi << 8)
      out[i] = value > 0x7fff ? value - 0x10000 : value
    }
    return out
  }

  reset(): void {
    // Stateless: each frame decodes independently.
  }

  close(): void {
    // No resources to release.
  }
}

// --- mu-law (ITU-T G.711) ---------------------------------------------------

const MULAW_TABLE: Int16Array = (() => {
  const table = new Int16Array(256)
  for (let i = 0; i < 256; i += 1) {
    const value = ~i & 0xff
    const sign = value & 0x80
    const exponent = (value >> 4) & 0x07
    const mantissa = value & 0x0f
    let sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    table[i] = sign !== 0 ? -sample : sample
  }
  return table
})()

export class MuLawDecoder implements AudioDecoder {
  readonly hasFullSupport = true
  readonly isAsync = false
  readonly ready = RESOLVED

  constructor(readonly codec: BleAudioCodec) {}

  decode(frame: Uint8Array): Int16Array | null {
    const out = new Int16Array(frame.length)
    for (let i = 0; i < frame.length; i += 1) {
      out[i] = MULAW_TABLE[frame[i]]
    }
    return out
  }

  reset(): void {
    // Stateless: the lookup table is shared and immutable.
  }

  close(): void {
    // No resources to release.
  }
}

// --- LC3 placeholder --------------------------------------------------------

/** LC3 needs liblc3, which neither platform ships; macOS emits silence of the
 *  right length so timing stays correct, and this does the same. */
export class Lc3SilenceDecoder implements AudioDecoder {
  readonly codec: BleAudioCodec = 'lc3FS1030'
  readonly hasFullSupport = false
  readonly isAsync = false
  readonly ready = RESOLVED

  /** 30-byte frames represent 10 ms at 16 kHz. */
  private static readonly SAMPLES_PER_FRAME = 160

  decode(frame: Uint8Array): Int16Array | null {
    if (frame.length === 0) return null
    return new Int16Array(Lc3SilenceDecoder.SAMPLES_PER_FRAME)
  }

  reset(): void {
    // Stateless: every frame maps to the same silence buffer length.
  }

  close(): void {
    // No resources to release.
  }
}
