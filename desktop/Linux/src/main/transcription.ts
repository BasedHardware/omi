import { ipcMain, WebContents } from 'electron'
import WebSocket from 'ws'
import { getValidToken } from './auth'
import { pythonBaseURL } from './env'
import { settings } from './settings'
import type { TranscribeEvent } from '../shared/types'

// Bridge between renderer audio capture and the Python backend WebSockets, mirroring
// TranscriptionService.swift. Conversation mode -> /v4/listen (16 kHz mono PCM16,
// segments + memory events); PTT mode -> /v2/voice-message/transcribe-stream
// (interim/final, "finalize" text frame ends the turn).
//
// Conversation mode auto-reconnects with exponential backoff if the socket drops
// mid-recording (matching the Swift watchdog/reconnect). PTT is a single short
// turn, so it does not reconnect.

type Mode = 'conversation' | 'ptt'

const MAX_RECONNECTS = 10
const MAX_QUEUED_FRAMES = 500 // ~64s of 16 kHz mono PCM16 at 128 ms/frame

class TranscriptionBridge {
  private ws: WebSocket | null = null
  private mode: Mode = 'conversation'
  private sender: WebContents | null = null
  private channel = ''
  private active = false // a session the user wants kept alive
  private queue: Buffer[] = []
  private reconnects = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private language = 'en'
  private gen = 0 // bumped on every start/teardown so a superseded async connect can bail

  private emit(event: TranscribeEvent): void {
    if (this.sender && !this.sender.isDestroyed()) this.sender.send(this.channel, event)
  }

  private socketUrl(base: string): string {
    const ws = base.replace(/^http/, 'ws')
    return this.mode === 'conversation'
      ? `${ws}v4/listen?language=${encodeURIComponent(this.language)}&sample_rate=16000&codec=pcm16&channels=1` +
          `&include_speech_profile=true&source=desktop&speaker_auto_assign=enabled`
      : `${ws}v2/voice-message/transcribe-stream?language=${encodeURIComponent(this.language)}&sample_rate=16000&encoding=linear16&channels=1`
  }

  async start(sender: WebContents, channel: string, mode: Mode, language?: string): Promise<boolean> {
    this.teardown(false)
    this.sender = sender
    this.channel = channel
    this.mode = mode
    this.language = language || settings.get().transcriptionLanguage || 'en'
    this.active = true
    this.reconnects = 0
    this.queue = []
    return this.connect()
  }

  private async connect(): Promise<boolean> {
    const myGen = this.gen
    const token = await getValidToken()
    if (!token) {
      this.emit({ type: 'status', status: 'error', detail: 'not signed in' })
      this.active = false
      return false
    }
    // A stop() or a newer start() during the token await supersedes this connect.
    // Bail before creating a socket so we never leak an orphaned OPEN connection.
    if (this.gen !== myGen || !this.active) return false

    const url = this.socketUrl(pythonBaseURL())
    this.emit({ type: 'status', status: 'connecting' })
    const ws = new WebSocket(url, { headers: { Authorization: `Bearer ${token}` } })
    this.ws = ws

    ws.on('open', () => {
      this.reconnects = 0
      this.emit({ type: 'status', status: 'connected' })
      for (const buf of this.queue.splice(0)) {
        if (ws.readyState === WebSocket.OPEN) ws.send(buf)
      }
    })
    ws.on('message', (data, isBinary) => {
      if (isBinary) return
      this.handleMessage(data.toString())
    })
    ws.on('close', () => {
      if (this.ws === ws) this.ws = null
      this.handleDrop()
    })
    ws.on('error', (err) => {
      this.emit({ type: 'status', status: 'error', detail: String(err) })
      // 'close' fires after 'error'; reconnect is handled there.
    })
    return true
  }

  private handleMessage(text: string): void {
    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch {
      return // non-JSON frames ignored, same as the Mac client
    }
    if (Array.isArray(parsed)) {
      this.emit({ type: 'segments', segments: parsed })
      return
    }
    if (!parsed || typeof parsed !== 'object') return
    const p = parsed as Record<string, unknown>
    if (p.type === 'interim' || (p.is_final === false && typeof p.text === 'string')) {
      this.emit({ type: 'interim', text: String(p.text) })
    } else if (p.type === 'final' || (p.is_final === true && typeof p.text === 'string')) {
      this.emit({ type: 'final', text: String(p.text) })
    } else if (p.segment) {
      this.emit({ type: 'segments', segments: [p.segment as never] })
    } else {
      this.emit({ type: 'message', payload: p })
    }
  }

  private handleDrop(): void {
    if (!this.active) return // user-initiated stop
    // PTT is a single short turn, don't reconnect, just report closed.
    if (this.mode === 'ptt') {
      this.active = false
      this.emit({ type: 'status', status: 'closed' })
      return
    }
    if (this.reconnects >= MAX_RECONNECTS) {
      this.active = false
      this.emit({ type: 'status', status: 'closed', detail: 'reconnect limit reached' })
      return
    }
    const delay = Math.min(8000, 500 * 2 ** this.reconnects)
    this.reconnects++
    this.emit({ type: 'status', status: 'connecting', detail: `reconnecting (${this.reconnects})` })
    this.reconnectTimer = setTimeout(() => {
      if (this.active) void this.connect()
    }, delay)
  }

  sendAudio(chunk: ArrayBuffer): void {
    const buf = Buffer.from(chunk)
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(buf)
    } else if (this.active && this.queue.length < MAX_QUEUED_FRAMES) {
      // Buffer across connecting / reconnect-backoff gaps so we don't drop audio.
      this.queue.push(buf)
    }
  }

  finalize(): void {
    if (this.mode === 'ptt' && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send('finalize')
    }
  }

  /** Tear down the socket. emitClosed=false during a fresh start (no stale event). */
  private teardown(emitClosed: boolean): void {
    const had = this.active || this.ws !== null
    this.gen++
    this.active = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      const ws = this.ws
      this.ws = null
      try {
        ws.removeAllListeners('close')
        ws.close(1000)
      } catch {
        // ignore
      }
    }
    this.queue = []
    if (emitClosed && had) this.emit({ type: 'status', status: 'closed' })
  }

  stop(): void {
    this.teardown(true)
  }
}

const conversationBridge = new TranscriptionBridge()
const pttBridge = new TranscriptionBridge()

export function registerTranscriptionIpc(): void {
  ipcMain.handle('transcribe:start', (e, mode: Mode, language?: string) => {
    const bridge = mode === 'ptt' ? pttBridge : conversationBridge
    return bridge.start(e.sender, `transcribe:event:${mode}`, mode, language)
  })
  ipcMain.on('transcribe:audio', (_e, mode: Mode, chunk: ArrayBuffer) => {
    const bridge = mode === 'ptt' ? pttBridge : conversationBridge
    bridge.sendAudio(chunk)
  })
  ipcMain.on('transcribe:finalize', (_e, mode: Mode) => {
    const bridge = mode === 'ptt' ? pttBridge : conversationBridge
    bridge.finalize()
  })
  ipcMain.on('transcribe:stop', (_e, mode: Mode) => {
    const bridge = mode === 'ptt' ? pttBridge : conversationBridge
    bridge.stop()
  })
}
