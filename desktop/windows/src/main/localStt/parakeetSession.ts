import WebSocket from 'ws'
import type { BackendSegment, ListenSource } from '../../shared/types'

const CONNECT_TIMEOUT_MS = 5000
const FINALIZE_TIMEOUT_MS = 8000

type ParakeetSegment = Record<string, unknown>

type ParakeetStreamHandlers = {
  onConnected: () => void
  onSegments: (segments: BackendSegment[]) => void
  onError: (message: string, fatal: boolean) => void
  onClosed: (code: number, reason: string) => void
}

function parseSpeakerId(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return undefined
  const match = value.match(/(\d+)/)
  if (!match) return undefined
  const parsed = Number(match[1])
  return Number.isFinite(parsed) ? parsed : undefined
}

function num(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

export function normalizeParakeetSegment(args: {
  raw: ParakeetSegment
  source: ListenSource
  sessionId: string
  sequence: number
  fallbackStart: number
}): BackendSegment | null {
  const text = typeof args.raw.text === 'string' ? args.raw.text.trim() : ''
  if (!text) return null

  const start = Math.max(0, num(args.raw.start, args.fallbackStart))
  const end = Math.max(start + 0.01, num(args.raw.end, start + 0.01))
  const speakerRaw = args.raw.speaker
  const speaker =
    typeof speakerRaw === 'string' && speakerRaw.trim() ? speakerRaw.trim() : undefined
  const speakerId = parseSpeakerId(args.raw.speaker_id ?? speaker)
  const personId = typeof args.raw.person_id === 'string' ? args.raw.person_id : undefined

  return {
    id: `local-${args.sessionId}-${args.sequence}`,
    text,
    speaker,
    speaker_id: speakerId,
    is_user: args.source === 'mic' ? true : Boolean(args.raw.is_user),
    person_id: personId,
    start,
    end
  }
}

function streamUrl(baseUrl: string): string {
  const wsBase = baseUrl
    .replace(/^http:/, 'ws:')
    .replace(/^https:/, 'wss:')
    .replace(/\/+$/, '')
  return `${wsBase}/v3/stream?sample_rate=16000`
}

export class ParakeetStreamSession {
  private ws: WebSocket | null = null
  private closed = false
  private sequence = 0
  private lastEnd = 0
  private closePromise: Promise<void> | null = null

  constructor(
    private readonly args: {
      sessionId: string
      source: ListenSource
      baseUrl: string
      handlers: ParakeetStreamHandlers
    }
  ) {}

  async start(): Promise<void> {
    if (this.closed) throw new Error('local Parakeet session already closed')

    await new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(streamUrl(this.args.baseUrl))
      this.ws = ws
      let settled = false
      const timer = setTimeout(() => {
        if (settled) return
        settled = true
        this.closed = true
        try {
          ws.terminate()
        } catch {
          /* ignore */
        }
        reject(new Error('local Parakeet connect timeout'))
      }, CONNECT_TIMEOUT_MS)
      timer.unref?.()

      const settleFailure = (message: string): void => {
        if (!settled) {
          settled = true
          clearTimeout(timer)
          this.closed = true
          reject(new Error(message))
          return
        }
        this.args.handlers.onError(message, false)
      }

      ws.on('open', () => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        this.args.handlers.onConnected()
        resolve()
      })
      ws.on('message', (data, isBinary) => {
        if (isBinary) return
        this.handleMessage(data.toString())
      })
      ws.on('error', (err) => settleFailure(err.message))
      ws.on('close', (code, reasonBuf) => {
        this.closed = true
        if (!settled) {
          settled = true
          clearTimeout(timer)
          reject(new Error(`local Parakeet closed before connect (${code})`))
          return
        }
        this.args.handlers.onClosed(code, reasonBuf.toString())
      })
    })
  }

  feed(pcm: ArrayBuffer): void {
    if (this.closed || this.ws?.readyState !== WebSocket.OPEN) return
    this.ws.send(Buffer.from(new Uint8Array(pcm)))
  }

  async stop(): Promise<void> {
    if (this.closePromise) return this.closePromise
    this.closePromise = this.stopInner()
    return this.closePromise
  }

  private async stopInner(): Promise<void> {
    const ws = this.ws
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) return

    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        try {
          ws.terminate()
        } catch {
          /* ignore */
        }
        resolve()
      }, FINALIZE_TIMEOUT_MS)
      timer.unref?.()

      ws.once('close', () => {
        clearTimeout(timer)
        resolve()
      })

      try {
        ws.send('finalize')
      } catch {
        try {
          ws.close()
        } catch {
          /* ignore */
        }
      }
    })
  }

  private handleMessage(text: string): void {
    let payload: unknown
    try {
      payload = JSON.parse(text)
    } catch {
      return
    }

    const raws = Array.isArray(payload) ? payload : [payload]
    const segments: BackendSegment[] = []
    for (const raw of raws) {
      if (!raw || typeof raw !== 'object') continue
      const segment = normalizeParakeetSegment({
        raw: raw as ParakeetSegment,
        source: this.args.source,
        sessionId: this.args.sessionId,
        sequence: ++this.sequence,
        fallbackStart: this.lastEnd
      })
      if (!segment) continue
      this.lastEnd = Math.max(this.lastEnd, segment.end)
      segments.push(segment)
    }
    if (segments.length > 0) this.args.handlers.onSegments(segments)
  }
}
