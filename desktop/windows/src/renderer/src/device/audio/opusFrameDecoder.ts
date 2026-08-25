/**
 * Opus decoding through the WASM libopus build (opus-decoder). macOS uses
 * AudioToolbox's kAudioFormatOpus; the shared contract is 16 kHz mono output,
 * so the wire codec never leaves this layer.
 */

import { OpusDecoder } from 'opus-decoder'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import { CODEC_SAMPLE_RATE } from '../protocol/deviceTypes'
import { VALID_OPUS_TOC_BYTES, type AudioDecoder } from './audioCodecDecoder'

const floatToInt16 = (samples: Float32Array): Int16Array => {
  const out = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]))
    out[i] = Math.round(clamped * 32767)
  }
  return out
}

export class OpusFrameDecoder implements AudioDecoder {
  readonly hasFullSupport = true
  readonly isAsync = false
  readonly ready: Promise<void>

  private decoder: OpusDecoder | null = null
  private closed = false
  private loggedSuspectToc = false

  constructor(readonly codec: BleAudioCodec) {
    const decoder = new OpusDecoder({ channels: 1, sampleRate: CODEC_SAMPLE_RATE })
    this.ready = decoder.ready.then(() => {
      if (this.closed) {
        decoder.free()
        return
      }
      this.decoder = decoder
    })
  }

  decode(frame: Uint8Array): Int16Array | null {
    const decoder = this.decoder
    if (decoder === null || frame.length === 0) return null
    if (!VALID_OPUS_TOC_BYTES.has(frame[0]) && !this.loggedSuspectToc) {
      // Logged once per session: a wrong TOC usually means the framing is off,
      // not that this one packet is bad, and the decode is attempted anyway.
      this.loggedSuspectToc = true
      console.warn(
        `[device] opus frame with unexpected TOC 0x${frame[0].toString(16)} (${frame.length} bytes)`
      )
    }
    const result = decoder.decodeFrame(frame)
    if (result.errors.length > 0) return null
    const channel = result.channelData[0]
    if (channel === undefined || result.samplesDecoded <= 0) return null
    return floatToInt16(channel.subarray(0, result.samplesDecoded))
  }

  reset(): void {
    this.decoder?.reset()
  }

  close(): void {
    this.closed = true
    this.decoder?.free()
    this.decoder = null
  }
}
