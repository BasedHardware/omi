// Minimal ambient types for opus-decoder (ships JavaScript only, no types).
// Mirrors the subset of the WASM libopus wrapper the BLE audio path uses.
declare module 'opus-decoder' {
  export interface OpusDecodedAudio {
    channelData: Float32Array[]
    samplesDecoded: number
    sampleRate: number
    errors: Array<{ message: string; frameLength?: number; frameNumber?: number }>
  }

  export interface OpusDecoderOptions {
    channels?: number
    /** Output rate; libopus supports 8000, 12000, 16000, 24000, 48000. */
    sampleRate?: number
    preSkip?: number
    forceStereo?: boolean
    streamCount?: number
    coupledStreamCount?: number
    channelMappingTable?: number[]
  }

  export class OpusDecoder {
    constructor(options?: OpusDecoderOptions)
    readonly ready: Promise<void>
    decodeFrame(frame: Uint8Array): OpusDecodedAudio
    decodeFrames(frames: Uint8Array[]): OpusDecodedAudio
    reset(): void
    free(): void
  }
}
