import { ipcMain, WebContents } from 'electron'
import WebSocket from 'ws'
import { getValidToken } from './auth'
import { pythonBaseURL } from './env'
import { settings } from './settings'

// Realtime voice bridge, ported from RealtimeOmniService.swift. Connects to the
// Omi relay (wss://.../v1/omni/relay), which transparently proxies to the chosen
// provider's realtime API. We speak the provider's wire protocol directly.
// Gemini: 16 kHz PCM in, 24 kHz out. OpenAI: 24 kHz in/out.

type Provider = 'gemini' | 'openai'

const MODELS: Record<Provider, string> = {
  gemini: 'gemini-3.1-flash-live-preview',
  openai: 'gpt-realtime-2'
}

// Cap the pre-open send queue so a relay that never reaches 'open' (server down or a
// slow/hung handshake) while the renderer keeps streaming audio cannot grow main
// process memory without bound. Mirrors transcription's MAX_QUEUED_FRAMES.
const MAX_PENDING = 500

function resolveProvider(): Provider {
  const p = settings.get().realtimeProvider
  return p === 'openai' ? 'openai' : 'gemini' // 'auto' -> gemini (default pick)
}

class RealtimeBridge {
  private ws: WebSocket | null = null
  private sender: WebContents | null = null
  private provider: Provider = 'gemini'
  private open = false
  private pending: string[] = []
  private gen = 0 // bumped on stop so a superseded async start can bail

  inputRate(): number {
    return this.provider === 'openai' ? 24000 : 16000
  }

  private emit(event: Record<string, unknown>): void {
    if (this.sender && !this.sender.isDestroyed()) this.sender.send('realtime:event', event)
  }

  private sendJson(obj: unknown): void {
    const s = JSON.stringify(obj)
    if (this.ws && this.open) this.ws.send(s)
    else {
      if (this.pending.length >= MAX_PENDING) this.pending.shift()
      this.pending.push(s)
    }
  }

  async start(sender: WebContents): Promise<{ ok: boolean; inputRate: number; provider: Provider } | { ok: false }> {
    this.stop()
    const myGen = this.gen
    this.sender = sender
    this.provider = resolveProvider()
    const token = await getValidToken()
    if (!token) return { ok: false }
    // A stop() or newer start() during the token await supersedes this one; bail
    // before creating a socket so we don't leak an orphaned OPEN connection.
    if (this.gen !== myGen) return { ok: false }

    const base = pythonBaseURL().replace(/^http/, 'ws')
    const url = `${base}v1/omni/relay?provider=${this.provider}&model=${encodeURIComponent(MODELS[this.provider])}`
    const ws = new WebSocket(url, { headers: { Authorization: `Bearer ${token}` } })
    this.ws = ws

    ws.on('open', () => {
      this.open = true
      this.sendSessionSetup()
      for (const s of this.pending.splice(0)) ws.send(s)
      this.emit({ type: 'status', status: 'connected' })
    })
    ws.on('message', (data, isBinary) => {
      if (isBinary) return
      this.handleMessage(data.toString())
    })
    ws.on('close', () => {
      this.open = false
      this.ws = null
      this.emit({ type: 'status', status: 'closed' })
    })
    ws.on('error', (err) => {
      // Clear state so later sendJson calls re-queue instead of writing to a dead
      // or half-open socket. A 'close' usually follows and is idempotent here.
      this.open = false
      this.ws = null
      this.emit({ type: 'status', status: 'error', detail: String(err) })
    })
    return { ok: true, inputRate: this.inputRate(), provider: this.provider }
  }

  private sendSessionSetup(): void {
    if (this.provider === 'openai') {
      this.sendJson({
        type: 'session.update',
        session: {
          type: 'realtime',
          output_modalities: ['audio'],
          audio: {
            input: { format: { type: 'audio/pcm', rate: 24000 }, turn_detection: null, transcription: { model: 'whisper-1' } },
            output: { format: { type: 'audio/pcm', rate: 24000 }, voice: settings.get().ttsVoice || 'marin' }
          }
        }
      })
    } else {
      this.sendJson({
        setup: {
          model: `models/${MODELS.gemini}`,
          generationConfig: { responseModalities: ['AUDIO'] },
          inputAudioTranscription: {},
          outputAudioTranscription: {},
          realtimeInputConfig: { automaticActivityDetection: { disabled: true } }
        }
      })
    }
  }

  sendAudio(chunk: ArrayBuffer): void {
    const b64 = Buffer.from(chunk).toString('base64')
    if (this.provider === 'openai') {
      this.sendJson({ type: 'input_audio_buffer.append', audio: b64 })
    } else {
      this.sendJson({ realtimeInput: { audio: { data: b64, mimeType: 'audio/pcm;rate=16000' } } })
    }
  }

  commit(): void {
    if (this.provider === 'openai') {
      this.sendJson({ type: 'input_audio_buffer.commit' })
      this.sendJson({ type: 'response.create' })
    } else {
      this.sendJson({ realtimeInput: { activityEnd: {} } })
    }
  }

  private handleMessage(text: string): void {
    let msg: Record<string, unknown>
    try {
      msg = JSON.parse(text)
    } catch {
      return
    }
    if (this.provider === 'openai') {
      const type = msg.type as string
      if (type === 'conversation.item.input_audio_transcription.delta') {
        this.emit({ type: 'input_transcript', text: msg.delta, final: false })
      } else if (type === 'conversation.item.input_audio_transcription.completed') {
        this.emit({ type: 'input_transcript', text: msg.transcript, final: true })
      } else if (type === 'response.output_audio.delta') {
        this.emit({ type: 'audio', base64: msg.delta })
      } else if (type === 'response.output_audio_transcript.delta' || type === 'response.text.delta') {
        this.emit({ type: 'output_transcript', text: msg.delta })
      }
    } else {
      const sc = msg.serverContent as Record<string, unknown> | undefined
      const inputT = msg.inputTranscription as { text?: string } | undefined
      if (inputT?.text) this.emit({ type: 'input_transcript', text: inputT.text, final: false })
      if (sc) {
        const outT = sc.outputTranscription as { text?: string } | undefined
        if (outT?.text) this.emit({ type: 'output_transcript', text: outT.text })
        const modelTurn = sc.modelTurn as { parts?: { inlineData?: { data?: string } }[] } | undefined
        for (const part of modelTurn?.parts ?? []) {
          if (part.inlineData?.data) this.emit({ type: 'audio', base64: part.inlineData.data })
        }
      }
    }
  }

  stop(): void {
    this.gen++
    this.open = false
    this.pending = []
    if (this.ws) {
      try {
        this.ws.removeAllListeners('close')
        this.ws.close(1000)
      } catch {
        // ignore
      }
      this.ws = null
    }
  }
}

const bridge = new RealtimeBridge()

export function registerRealtimeIpc(): void {
  ipcMain.handle('realtime:start', (e) => bridge.start(e.sender))
  ipcMain.on('realtime:audio', (_e, chunk: ArrayBuffer) => bridge.sendAudio(chunk))
  ipcMain.on('realtime:commit', () => bridge.commit())
  ipcMain.on('realtime:stop', () => bridge.stop())
}
