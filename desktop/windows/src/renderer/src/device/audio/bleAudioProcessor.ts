/**
 * BLE audio processor — Windows port of macOS Audio/BleAudioProcessor.swift
 * (itself ported from the Flutter WavBytesUtil). Turns device frames into
 * 16 kHz mono PCM: fixed-size slicing for pre-framed families, Omi's
 * three-byte packet reassembly for the first-party device, and a decode
 * failure ladder that flags a degraded session after ten consecutive misses.
 */

import type { BleAudioCodec } from '../protocol/deviceTypes'
import { codecFrameLengthInBytes } from '../protocol/deviceTypes'
import type { AudioDecoder } from './audioCodecDecoder'
import { createAudioDecoder } from './audioDecoderFactory'

export const MAX_CONSECUTIVE_DECODE_FAILURES = 10

/** Fixed slice widths for families that ship pre-framed audio. */
const FRAMED_SLICE_BYTES: Partial<Record<BleAudioCodec, number>> = {
  opusFS320: 40,
  lc3FS1030: 30
}

export interface BleAudioProcessorStats {
  framesProcessed: number
  bytesProcessed: number
  lostPackets: number
  decodeFailures: number
}

export interface BleAudioProcessorDelegate {
  onPcm(pcm: Int16Array): void
  /** Fires once when the failure ladder trips, and again on recovery. */
  onDegradedChange(isDegraded: boolean, detail: { codec: BleAudioCodec; failures: number }): void
}

export class BleAudioProcessor {
  readonly codec: BleAudioCodec
  private readonly decoder: AudioDecoder | null
  private readonly delegate: BleAudioProcessorDelegate

  private pendingFrame: Uint8Array[] = []
  private pendingFrameBytes = 0
  private lastPacketIndex: number | null = null
  private lastFrameId: number | null = null

  private consecutiveDecodeFailures = 0
  private degraded = false
  private stats: BleAudioProcessorStats = {
    framesProcessed: 0,
    bytesProcessed: 0,
    lostPackets: 0,
    decodeFailures: 0
  }

  constructor(args: { codec: BleAudioCodec; delegate: BleAudioProcessorDelegate }) {
    this.codec = args.codec
    this.delegate = args.delegate
    this.decoder = createAudioDecoder(args.codec, {
      onPcm: (pcm) => this.emitPcm(pcm),
      onError: (error) => this.handleDecodeFailure(error.message)
    })
  }

  get hasDecoder(): boolean {
    return this.decoder !== null
  }

  get hasFullSupport(): boolean {
    return this.decoder?.hasFullSupport ?? false
  }

  get isDegraded(): boolean {
    return this.degraded
  }

  get snapshot(): BleAudioProcessorStats {
    return { ...this.stats }
  }

  /** Resolves once the decoder can accept frames (WASM init). */
  ready(): Promise<void> {
    return this.decoder?.ready ?? Promise.resolve()
  }

  /** Entry point for families whose notifications are not pre-framed. */
  processAudioData(data: Uint8Array): void {
    this.stats.bytesProcessed += data.length
    const sliceWidth = FRAMED_SLICE_BYTES[this.codec]
    if (sliceWidth !== undefined) {
      this.processFramedData(data, sliceWidth)
      return
    }
    this.processPacketData(data)
  }

  /** Entry point for families whose connection already emits whole frames. */
  processFrame(frame: Uint8Array): void {
    this.stats.bytesProcessed += frame.length
    this.decodeFrame(frame)
  }

  private processFramedData(data: Uint8Array, sliceWidth: number): void {
    let offset = 0
    while (offset + sliceWidth <= data.length) {
      this.decodeFrame(data.subarray(offset, offset + sliceWidth))
      offset += sliceWidth
    }
    if (offset < data.length) {
      // A partial tail cannot be decoded and joining it to the next
      // notification would misalign every following frame.
      console.warn(`[device] dropping ${data.length - offset} byte partial ${this.codec} frame`)
    }
  }

  /** Omi/OpenGlass packet framing: [u16 index LE, u8 frameId, ...content]. */
  private processPacketData(packet: Uint8Array): void {
    if (packet.length < 3) return
    const packetIndex = packet[0] | (packet[1] << 8)
    const frameId = packet[2]
    const content = packet.subarray(3)

    if (this.lastPacketIndex !== null) {
      const lost = packetIndex - this.lastPacketIndex - 1
      if (lost > 0 && lost < 100) {
        this.stats.lostPackets += lost
        this.resetPendingFrame()
      } else if (lost !== 0) {
        // A jump this large is a counter wrap or a reconnect, not loss.
        this.resetPendingFrame()
      }
    }
    this.lastPacketIndex = packetIndex

    if (frameId === 0) {
      this.flushPendingFrame()
      this.pendingFrame = [content.slice()]
      this.pendingFrameBytes = content.length
      this.lastFrameId = 0
    } else if (this.lastFrameId !== null && frameId === this.lastFrameId + 1) {
      this.pendingFrame.push(content.slice())
      this.pendingFrameBytes += content.length
      this.lastFrameId = frameId
    } else {
      this.resetPendingFrame()
      return
    }

    if (this.pendingFrameBytes >= codecFrameLengthInBytes(this.codec)) {
      this.flushPendingFrame()
    }
  }

  private flushPendingFrame(): void {
    if (this.pendingFrameBytes === 0) {
      this.resetPendingFrame()
      return
    }
    const frame = new Uint8Array(this.pendingFrameBytes)
    let offset = 0
    for (const chunk of this.pendingFrame) {
      frame.set(chunk, offset)
      offset += chunk.length
    }
    this.resetPendingFrame()
    this.decodeFrame(frame)
  }

  private resetPendingFrame(): void {
    this.pendingFrame = []
    this.pendingFrameBytes = 0
    this.lastFrameId = null
  }

  private decodeFrame(frame: Uint8Array): void {
    const decoder = this.decoder
    if (decoder === null) {
      this.handleDecodeFailure('no decoder for codec')
      return
    }
    let pcm: Int16Array | null = null
    try {
      pcm = decoder.decode(frame)
    } catch (error) {
      this.handleDecodeFailure(error instanceof Error ? error.message : String(error))
      return
    }
    if (pcm === null) {
      // Async decoders deliver through the sink, so null is normally "pending".
      // But an async decoder that reports no real support (WebCodecs missing)
      // will never deliver anything, and treating its nulls as pending would
      // make a permanently silent session look healthy.
      if (!decoder.isAsync || !decoder.hasFullSupport) {
        this.handleDecodeFailure(`decoder returned no samples for ${frame.length} bytes`)
      }
      return
    }
    this.emitPcm(pcm)
  }

  private emitPcm(pcm: Int16Array): void {
    this.stats.framesProcessed += 1
    this.consecutiveDecodeFailures = 0
    if (this.degraded) {
      this.degraded = false
      this.delegate.onDegradedChange(false, { codec: this.codec, failures: 0 })
    }
    this.delegate.onPcm(pcm)
  }

  private handleDecodeFailure(detail: string): void {
    this.stats.decodeFailures += 1
    this.consecutiveDecodeFailures += 1
    if (this.consecutiveDecodeFailures === 1) {
      console.warn(`[device] ${this.codec} decode failed: ${detail}`)
    }
    if (this.consecutiveDecodeFailures === MAX_CONSECUTIVE_DECODE_FAILURES && !this.degraded) {
      this.degraded = true
      console.error(
        `[device] failure_class=ble_decode_degraded codec=${this.codec} ` +
          `failures=${this.consecutiveDecodeFailures}`
      )
      this.delegate.onDegradedChange(true, {
        codec: this.codec,
        failures: this.consecutiveDecodeFailures
      })
    }
  }

  reset(): void {
    this.resetPendingFrame()
    this.lastPacketIndex = null
    this.consecutiveDecodeFailures = 0
    this.decoder?.reset()
  }

  close(): void {
    this.decoder?.close()
  }
}
