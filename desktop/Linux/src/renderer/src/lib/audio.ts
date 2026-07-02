// Microphone (+ optional WASAPI loopback system audio) capture, downsampled to
// 16 kHz mono PCM16, the renderer half of the Mac AudioSourceManager pipeline.

/**
 * Boost a raw RMS level (0..1) the way AudioLevelWaveformView does: a square-root
 * curve amplified 2.5x so quiet speech is still visible, clamped to 1.
 */
export function boostedLevel(level: number): number {
  if (!Number.isFinite(level) || level <= 0) return 0
  return Math.min(1, Math.sqrt(level) * 2.5)
}

/**
 * Per-bar height (px) for the 12-bar live waveform, ported from
 * AudioLevelWaveformView.BarView.barHeight: center bars run up to 40% taller,
 * plus a deterministic per-bar wobble for an organic feel. Range ~6..32px.
 */
export function waveformBarHeight(
  level: number,
  index: number,
  totalBars: number,
  isActive = true,
  minHeight = 6,
  maxHeight = 32
): number {
  if (!isActive) return minHeight
  const clamped = boostedLevel(level)
  const centerOffset = Math.abs(index - (totalBars - 1) / 2) / (totalBars / 2)
  const variation = 1 - centerOffset * 0.4
  const scaled = clamped * variation
  const hash = Math.sin(index * 1.618 + 0.5)
  const wobble = 0.85 + 0.3 * (hash * 0.5 + 0.5)
  const height = minHeight + (maxHeight - minHeight) * scaled * wobble
  return Math.max(minHeight, Math.min(maxHeight, height))
}

/**
 * Tier color for a waveform bar given the current level, matching
 * AudioLevelWaveformView.BarView.barColor's boosted-level thresholds.
 */
export function waveformBarColor(level: number, isActive = true): string {
  if (!isActive) return 'rgba(176,176,176,0.5)' // text-tertiary @ 0.5
  const boosted = boostedLevel(level)
  if (boosted > 0.6) return 'var(--purple-primary)'
  if (boosted > 0.2) return 'var(--text-primary)'
  if (boosted > 0.02) return 'var(--text-secondary)'
  return 'rgba(176,176,176,0.5)'
}

export interface PcmCaptureOptions {
  systemAudio: boolean
  sampleRate?: number
  onFrame: (frame: ArrayBuffer) => void
  onLevel?: (rms: number) => void
}

export class PcmCapture {
  private ctx: AudioContext | null = null
  private micStream: MediaStream | null = null
  private displayStream: MediaStream | null = null
  private worklet: AudioWorkletNode | null = null
  private levelTimer: number | null = null

  async start(opts: PcmCaptureOptions): Promise<void> {
    this.ctx = new AudioContext({ sampleRate: opts.sampleRate ?? 16000 })
    await this.ctx.audioWorklet.addModule('pcm-worklet.js')

    const mix = this.ctx.createGain()
    mix.gain.value = 1

    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    })
    this.ctx.createMediaStreamSource(this.micStream).connect(mix)

    if (opts.systemAudio) {
      try {
        // Arm the main-process handler so this (app-initiated) request is honored;
        // out-of-band getDisplayMedia calls are denied. Resolves to primary
        // screen + 'loopback' audio.
        window.omi.capture.armLoopback()
        this.displayStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
        for (const track of this.displayStream.getVideoTracks()) track.stop()
        if (this.displayStream.getAudioTracks().length > 0) {
          const sysSource = this.ctx.createMediaStreamSource(this.displayStream)
          const sysGain = this.ctx.createGain()
          sysGain.gain.value = 0.8
          sysSource.connect(sysGain).connect(mix)
        }
      } catch (e) {
        console.warn('system audio capture unavailable, continuing with mic only', e)
      }
    }

    this.worklet = new AudioWorkletNode(this.ctx, 'pcm-processor', {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1,
      channelCountMode: 'explicit',
      channelInterpretation: 'speakers'
    })
    this.worklet.port.onmessage = (e) => opts.onFrame(e.data as ArrayBuffer)
    mix.connect(this.worklet)

    if (opts.onLevel) {
      const analyser = this.ctx.createAnalyser()
      analyser.fftSize = 512
      mix.connect(analyser)
      const data = new Float32Array(analyser.fftSize)
      const tick = () => {
        analyser.getFloatTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i]
        opts.onLevel?.(Math.sqrt(sum / data.length))
        this.levelTimer = window.setTimeout(tick, 80)
      }
      tick()
    }
  }

  stop(): void {
    if (this.levelTimer) {
      clearTimeout(this.levelTimer)
      this.levelTimer = null
    }
    const workletPort = this.worklet?.port
    workletPort?.postMessage({ type: 'flush' })
    window.setTimeout(() => workletPort?.close(), 0)
    this.worklet = null
    for (const t of this.micStream?.getTracks() ?? []) t.stop()
    for (const t of this.displayStream?.getTracks() ?? []) t.stop()
    this.micStream = null
    this.displayStream = null
    void this.ctx?.close()
    this.ctx = null
  }
}
