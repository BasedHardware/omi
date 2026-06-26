import { PcmCapture } from './audio'

// Drives a realtime voice session: captures mic PCM at the provider's rate,
// streams it to the main-process relay bridge, and plays the 24 kHz PCM audio
// that comes back gaplessly. Counterpart of the floating bar's realtime hookup
// in RealtimeOmniService.swift.

const OUTPUT_RATE = 24000

export interface RealtimeHandlers {
  onInputTranscript?: (text: string, final: boolean) => void
  onOutputTranscript?: (text: string) => void
  onStatus?: (status: string, detail?: string) => void
}

export class RealtimeVoice {
  private capture: PcmCapture | null = null
  private playCtx: AudioContext | null = null
  private playHead = 0
  private unsub: (() => void) | null = null
  private active = false

  async start(handlers: RealtimeHandlers): Promise<boolean> {
    this.stop()
    const res = await window.omi.realtime.start()
    if (!res.ok) {
      handlers.onStatus?.('error', 'not signed in')
      return false
    }
    this.active = true
    this.playCtx = new AudioContext({ sampleRate: OUTPUT_RATE })
    this.playHead = this.playCtx.currentTime

    this.unsub = window.omi.realtime.onEvent((ev) => {
      const type = ev.type as string
      if (type === 'audio' && typeof ev.base64 === 'string') {
        this.enqueueAudio(ev.base64)
      } else if (type === 'input_transcript') {
        handlers.onInputTranscript?.(String(ev.text ?? ''), !!ev.final)
      } else if (type === 'output_transcript') {
        handlers.onOutputTranscript?.(String(ev.text ?? ''))
      } else if (type === 'status') {
        handlers.onStatus?.(String(ev.status), ev.detail ? String(ev.detail) : undefined)
      }
    })

    this.capture = new PcmCapture()
    try {
      await this.capture.start({
        systemAudio: false,
        sampleRate: res.inputRate ?? 16000,
        onFrame: (frame) => window.omi.realtime.sendAudio(frame)
      })
    } catch (e) {
      handlers.onStatus?.('error', `microphone unavailable: ${e}`)
      this.stop()
      return false
    }
    return true
  }

  /** Signal end-of-turn so the model responds. */
  commit(): void {
    if (this.active) window.omi.realtime.commit()
  }

  private enqueueAudio(b64: string): void {
    if (!this.playCtx) return
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.byteLength / 2))
    if (pcm.length === 0) return
    const buffer = this.playCtx.createBuffer(1, pcm.length, OUTPUT_RATE)
    const ch = buffer.getChannelData(0)
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000
    const src = this.playCtx.createBufferSource()
    src.buffer = buffer
    src.connect(this.playCtx.destination)
    const now = this.playCtx.currentTime
    if (this.playHead < now) this.playHead = now
    src.start(this.playHead)
    this.playHead += buffer.duration
  }

  stop(): void {
    this.active = false
    this.unsub?.()
    this.unsub = null
    this.capture?.stop()
    this.capture = null
    window.omi.realtime.stop()
    void this.playCtx?.close()
    this.playCtx = null
  }
}
