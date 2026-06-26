// Downstream of AudioSourceManager.swift's mixer: emits 2048-sample (128 ms @ 16 kHz)
// Int16 mono PCM frames, the exact frame size the Mac app streams to /v4/listen.
const FRAME_SIZE = 2048
const RING_SIZE = FRAME_SIZE * 16

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.ring = new Float32Array(RING_SIZE)
    this.readIndex = 0
    this.writeIndex = 0
    this.available = 0
    this.port.onmessage = (event) => {
      if (event.data && event.data.type === 'flush') this.flush()
    }
  }

  pushSamples(channel) {
    for (let i = 0; i < channel.length; i++) {
      this.ring[this.writeIndex] = channel[i]
      this.writeIndex = (this.writeIndex + 1) % RING_SIZE
      if (this.available < RING_SIZE) {
        this.available++
      } else {
        this.readIndex = (this.readIndex + 1) % RING_SIZE
      }
    }
  }

  emitFrame(padTail) {
    const pcm = new Int16Array(FRAME_SIZE)
    const count = padTail ? this.available : FRAME_SIZE
    for (let i = 0; i < FRAME_SIZE; i++) {
      const sample = i < count ? this.ring[this.readIndex] : 0
      if (i < count) this.readIndex = (this.readIndex + 1) % RING_SIZE
      const s = Math.max(-1, Math.min(1, sample))
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    this.available = Math.max(0, this.available - count)
    this.port.postMessage(pcm.buffer, [pcm.buffer])
  }

  flush() {
    if (this.available <= 0) return
    this.emitFrame(true)
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (channel && channel.length) {
      this.pushSamples(channel)
      while (this.available >= FRAME_SIZE) this.emitFrame(false)
    }
    return true
  }
}

registerProcessor('pcm-processor', PCMProcessor)
