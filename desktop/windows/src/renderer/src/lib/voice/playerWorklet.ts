// AudioWorklet entry — registered as 'omi-voice-player' and loaded via
// `?worker&url` by pcmPlayer (a plain `?url` import ships RAW TypeScript in prod
// builds — the Phase 2 lesson). Deliberately thin: all jitter-buffer logic lives
// in playerCore (node-tested). Runs in AudioWorkletGlobalScope, whose globals
// aren't in lib.dom, so declare the minimum surface we touch.
//
// Port protocol (main thread → worklet):
//   { type: 'pcm', buffer: ArrayBuffer }   Float32 samples to enqueue (transferred)
//   { type: 'clear' }                      barge-in: drop everything now
// (worklet → main thread):
//   { type: 'started' }                    a burst began audibly playing
//   { type: 'drained' }                    the burst's buffer fully drained
//   { type: 'level', value }               throttled linear 0..1 peak of the
//                                          audio actually played (~31Hz while
//                                          playing, one trailing 0 at burst end)
//                                          — the orb's speaking-pose amplitude
import { PlayerCore, PlaybackLevelMeter } from './playerCore'

declare abstract class AudioWorkletProcessor {
  readonly port: MessagePort
}
declare function registerProcessor(
  name: string,
  ctor: new (options?: never) => AudioWorkletProcessor
): void

class OmiVoicePlayerProcessor extends AudioWorkletProcessor {
  private readonly core: PlayerCore
  private readonly meter = new PlaybackLevelMeter()
  private wasPlaying = false

  constructor(options?: { processorOptions?: { cushionSamples?: number } }) {
    super()
    this.core = new PlayerCore(options?.processorOptions?.cushionSamples ?? 3600)
    this.port.onmessage = (e: MessageEvent<{ type: string; buffer?: ArrayBuffer }>): void => {
      const msg = e.data
      if (msg.type === 'pcm' && msg.buffer) {
        this.core.enqueue(new Float32Array(msg.buffer))
      } else if (msg.type === 'flush') {
        // End of turn: play any sub-cushion tail instead of withholding it.
        this.core.flush()
      } else if (msg.type === 'clear') {
        if (this.core.clear()) {
          this.wasPlaying = false
          this.port.postMessage({ type: 'drained' })
        }
      }
    }
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const channel = outputs[0]?.[0]
    if (!channel) return true
    if (!this.wasPlaying && this.core.playing) {
      this.wasPlaying = true
      this.port.postMessage({ type: 'started' })
    }
    const r = this.core.pull(channel)
    const level = this.meter.observe(channel, r.wroteAudio)
    if (level !== null) this.port.postMessage({ type: 'level', value: level })
    if (r.drained && this.wasPlaying) {
      this.wasPlaying = false
      this.port.postMessage({ type: 'drained' })
    }
    return true // keep alive for the session
  }
}

registerProcessor('omi-voice-player', OmiVoicePlayerProcessor)
