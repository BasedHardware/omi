/**
 * AAC decoding for Bee, through Chromium's WebCodecs AudioDecoder (macOS uses
 * AudioToolbox). Bee ships raw ADTS frames, and WebCodecs decodes ADTS when
 * the config carries no description, so the frames go through untouched.
 *
 * WebCodecs delivers PCM asynchronously, which is the one place this pipeline
 * cannot be synchronous; the processor hands such decoders a sink instead of
 * reading decode()'s return value.
 */

import type { BleAudioCodec } from '../protocol/deviceTypes'
import { CODEC_SAMPLE_RATE } from '../protocol/deviceTypes'
import type { AudioDecoder, AudioDecoderSinks } from './audioCodecDecoder'

const ADTS_HEADER_MIN_BYTES = 7

interface AudioDataLike {
  numberOfFrames: number
  numberOfChannels: number
  format: string | null
  copyTo(destination: ArrayBufferView, options: { planeIndex: number; format?: string }): void
  close(): void
}

interface WebCodecsAudioDecoder {
  state: string
  configure(config: { codec: string; sampleRate: number; numberOfChannels: number }): void
  decode(chunk: unknown): void
  close(): void
}

interface WebCodecsGlobals {
  AudioDecoder?: {
    new (init: {
      output: (data: AudioDataLike) => void
      error: (error: Error) => void
    }): WebCodecsAudioDecoder
  }
  EncodedAudioChunk?: new (init: {
    type: 'key' | 'delta'
    timestamp: number
    data: Uint8Array
  }) => unknown
}

/** Frame duration in microseconds: AAC-LC emits 1024 samples per frame. */
const FRAME_DURATION_US = Math.round((1024 / CODEC_SAMPLE_RATE) * 1_000_000)

export class AacFrameDecoder implements AudioDecoder {
  readonly codec: BleAudioCodec = 'aac'
  readonly hasFullSupport: boolean
  readonly isAsync = true
  readonly ready: Promise<void>

  private decoder: WebCodecsAudioDecoder | null = null
  private timestampUs = 0

  constructor(
    private readonly sinks: AudioDecoderSinks,
    globals: WebCodecsGlobals = globalThis as unknown as WebCodecsGlobals
  ) {
    const Decoder = globals.AudioDecoder
    const Chunk = globals.EncodedAudioChunk
    if (Decoder === undefined || Chunk === undefined) {
      // No WebCodecs: Bee audio cannot be decoded here, and the caller
      // surfaces that as an unsupported codec rather than silent dead air.
      this.hasFullSupport = false
      this.ready = Promise.resolve()
      return
    }
    this.hasFullSupport = true
    this.chunkConstructor = Chunk
    const decoder = new Decoder({
      output: (data) => this.handleOutput(data),
      error: (error) => this.sinks.onError(error)
    })
    // 'mp4a.40.2' with no description means ADTS-framed input.
    decoder.configure({
      codec: 'mp4a.40.2',
      sampleRate: CODEC_SAMPLE_RATE,
      numberOfChannels: 1
    })
    this.decoder = decoder
    this.ready = Promise.resolve()
  }

  private chunkConstructor: NonNullable<WebCodecsGlobals['EncodedAudioChunk']> | null = null

  decode(frame: Uint8Array): Int16Array | null {
    const decoder = this.decoder
    const Chunk = this.chunkConstructor
    if (decoder === null || Chunk === null || decoder.state === 'closed') return null
    if (frame.length < ADTS_HEADER_MIN_BYTES) {
      this.sinks.onError(new Error(`AAC frame shorter than an ADTS header (${frame.length} bytes)`))
      return null
    }
    decoder.decode(new Chunk({ type: 'key', timestamp: this.timestampUs, data: frame }))
    this.timestampUs += FRAME_DURATION_US
    return null
  }

  private handleOutput(data: AudioDataLike): void {
    try {
      const sampleCount = data.numberOfFrames
      if (sampleCount <= 0) return
      // Ask for interleaved 16-bit; planar float is the common fallback.
      if (data.format === 's16' || data.format === 's16-planar') {
        const pcm = new Int16Array(sampleCount)
        data.copyTo(pcm, { planeIndex: 0 })
        this.sinks.onPcm(pcm)
        return
      }
      const floats = new Float32Array(sampleCount)
      data.copyTo(floats, { planeIndex: 0, format: 'f32-planar' })
      const pcm = new Int16Array(sampleCount)
      for (let i = 0; i < sampleCount; i += 1) {
        const clamped = Math.max(-1, Math.min(1, floats[i]))
        pcm[i] = Math.round(clamped * 32767)
      }
      this.sinks.onPcm(pcm)
    } catch (error) {
      this.sinks.onError(error instanceof Error ? error : new Error(String(error)))
    } finally {
      data.close()
    }
  }

  reset(): void {
    this.timestampUs = 0
  }

  close(): void {
    if (this.decoder !== null && this.decoder.state !== 'closed') {
      this.decoder.close()
    }
    this.decoder = null
  }
}
