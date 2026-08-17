/**
 * BLE audio service — Windows port of macOS Audio/BleAudioService.swift. Owns
 * one processing session at a time: reads the device codec, builds the
 * processor, routes each family's frames to the right entry point, and hands
 * decoded 16 kHz mono PCM to the transcription sink.
 *
 * Every device family is decoded here, so the wire codec never reaches the
 * socket; the lane always carries linear16.
 */

import type { BleAudioCodec } from '../protocol/deviceTypes'
import type { DeviceConnection } from '../connections/deviceConnection'
import { BleAudioProcessor } from './bleAudioProcessor'
import { hasFullCodecSupport, isCodecSupported } from './audioDecoderFactory'

export interface BleAudioSessionHandlers {
  /** Decoded 16 kHz mono s16 PCM, in capture order. */
  onPcm: (pcm: Int16Array) => void
  /** The encoded device frame, for WAL capture, before any decoding. */
  onRawFrame?: (frame: Uint8Array) => void
  onCodec?: (codec: BleAudioCodec) => void
  onLevel?: (level: number) => void
  onDegradedChange?: (isDegraded: boolean) => void
  /** Fires when the device stream ends on its own (disconnect, teardown). */
  onEnded?: (error: Error | null) => void
}

export interface BleAudioSessionStats {
  framesProcessed: number
  bytesProcessed: number
  lostPackets: number
  decodeFailures: number
  durationMs: number
}

export class BleAudioService {
  private processing = false
  private generation = 0
  private processor: BleAudioProcessor | null = null
  private subscription: { cancel: () => void } | null = null
  private handlers: BleAudioSessionHandlers | null = null
  private startedAt = 0
  private codec: BleAudioCodec | null = null
  private level = 0
  private degraded = false

  get isProcessing(): boolean {
    return this.processing
  }

  get currentCodec(): BleAudioCodec | null {
    return this.codec
  }

  get audioLevel(): number {
    return this.level
  }

  get isDecodeDegraded(): boolean {
    return this.degraded
  }

  /**
   * Starts decoding the connection's audio. The processing slot is claimed
   * synchronously, before the first await, so two overlapping starts cannot
   * both build a processor.
   */
  async startProcessing(
    connection: DeviceConnection,
    handlers: BleAudioSessionHandlers
  ): Promise<boolean> {
    if (this.processing) {
      console.warn('[device] BLE audio processing already running')
      return false
    }
    this.processing = true
    const generation = ++this.generation
    this.handlers = handlers
    this.startedAt = Date.now()
    this.level = 0
    this.degraded = false

    let codec: BleAudioCodec
    try {
      codec = await connection.getAudioCodec()
    } catch (error) {
      // The slot is claimed synchronously, so a throw anywhere in setup has to
      // release it or every later start is refused as already running.
      console.error(`[device] failed to read the device audio codec: ${String(error)}`)
      this.stopProcessing()
      return false
    }
    // A stop can land during the codec read; that start is stale.
    if (!this.processing || this.generation !== generation) return false

    this.codec = codec
    handlers.onCodec?.(codec)

    if (!isCodecSupported(codec)) {
      console.error(`[device] unsupported audio codec ${codec}; not starting BLE audio`)
      this.stopProcessing()
      return false
    }
    if (!hasFullCodecSupport(codec)) {
      console.warn(`[device] ${codec} has partial support; audio quality may be affected`)
    }

    const processor = new BleAudioProcessor({
      codec,
      delegate: {
        onPcm: (pcm) => this.handleDecodedAudio(pcm, generation),
        onDegradedChange: (isDegraded) => {
          if (this.generation !== generation) return
          this.degraded = isDegraded
          handlers.onDegradedChange?.(isDegraded)
        }
      }
    })
    // No second decoder-existence check: createAudioDecoder covers the whole
    // codec union and returns null only for 'unknown', which the guard above
    // already rejected.
    try {
      await processor.ready()
    } catch (error) {
      console.error(`[device] audio decoder failed to initialize: ${String(error)}`)
      processor.close()
      this.stopProcessing()
      return false
    }
    if (!this.processing || this.generation !== generation) {
      processor.close()
      return false
    }
    this.processor = processor

    this.subscription = connection.getAudioStream({
      onValue: (frame) => {
        if (this.generation !== generation) return
        this.routeFrame(connection, frame)
      },
      onFinish: (error) => {
        if (this.generation !== generation) return
        // A stream that ends tears the whole session down, not just a flag.
        const ended = this.handlers?.onEnded
        this.stopProcessing()
        ended?.(error)
      }
    })
    return true
  }

  stopProcessing(): BleAudioSessionStats | null {
    if (!this.processing) return null
    this.processing = false
    this.generation += 1
    this.subscription?.cancel()
    this.subscription = null
    const processor = this.processor
    const stats = processor?.snapshot ?? null
    processor?.reset()
    processor?.close()
    this.processor = null
    this.handlers = null
    this.codec = null
    this.level = 0
    if (stats === null) return null
    const sessionStats: BleAudioSessionStats = {
      ...stats,
      durationMs: Date.now() - this.startedAt
    }
    console.info(
      `[device] BLE audio session ended: ${sessionStats.framesProcessed} frames, ` +
        `${sessionStats.bytesProcessed} bytes, ${sessionStats.lostPackets} lost packets, ` +
        `${sessionStats.decodeFailures} decode failures, ${sessionStats.durationMs} ms`
    )
    return sessionStats
  }

  /** Per-family frame routing: the connection layer already reassembles some
   *  families into whole frames, while others hand over raw notifications. */
  private routeFrame(connection: DeviceConnection, frame: Uint8Array): void {
    const processor = this.processor
    if (processor === null) return
    this.handlers?.onRawFrame?.(frame)
    switch (connection.device.type) {
      case 'bee':
      case 'limitless':
        processor.processFrame(frame)
        return
      default:
        processor.processAudioData(frame)
    }
  }

  private handleDecodedAudio(pcm: Int16Array, generation: number): void {
    if (this.generation !== generation) return
    this.updateAudioLevel(pcm)
    // Mono is deliberate: diarization happens server-side.
    this.handlers?.onPcm(pcm)
  }

  private updateAudioLevel(pcm: Int16Array): void {
    if (pcm.length === 0) return
    let sum = 0
    for (let i = 0; i < pcm.length; i += 1) {
      const sample = pcm[i] / 32768
      sum += sample * sample
    }
    const rms = Math.sqrt(sum / pcm.length)
    this.level = this.level * 0.7 + rms * 0.3
    this.handlers?.onLevel?.(this.level)
  }
}
