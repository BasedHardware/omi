// AudioWorklet entry — registered as 'omi-pcm' and loaded via `?url` by
// pcmPipeline. Deliberately thin: all logic lives in pcmWorkletCore (node-tested).
// Runs in AudioWorkletGlobalScope, whose globals aren't in lib.dom, so declare the
// minimum surface we touch.
import { PcmFramer } from './pcmWorkletCore'

declare const sampleRate: number
declare abstract class AudioWorkletProcessor {
  readonly port: MessagePort
}
declare function registerProcessor(
  name: string,
  ctor: new (options?: never) => AudioWorkletProcessor
): void

class OmiPcmProcessor extends AudioWorkletProcessor {
  private readonly framer: PcmFramer

  constructor(options?: {
    processorOptions?: { inputRate?: number; targetRate?: number; frameSamples?: number }
  }) {
    super()
    const o = options?.processorOptions ?? {}
    this.framer = new PcmFramer({
      inputRate: o.inputRate ?? sampleRate,
      targetRate: o.targetRate ?? 16000,
      frameSamples: o.frameSamples ?? 4096
    })
  }

  process(inputs: Float32Array[][]): boolean {
    const channel = inputs[0]?.[0]
    if (channel && channel.length > 0) {
      for (const frame of this.framer.push(channel)) {
        // Transfer the buffer so no copy crosses the worklet→main-thread port.
        this.port.postMessage(frame.buffer, [frame.buffer])
      }
    }
    return true // keep the processor alive for the session
  }
}

registerProcessor('omi-pcm', OmiPcmProcessor)
