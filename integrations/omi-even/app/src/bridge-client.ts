/** WebSocket client for the local omi bridge, with reconnect backoff.
 *
 *  The socket is treated as best-effort: the app never awaits a connection, it
 *  just reflects `status()` on the glasses. A dropped bridge shows up as
 *  "bridge offline" rather than a view that hangs forever.
 */
import { ASK_MAX_BUFFERED_BYTES, bridgeUrl } from './config.ts'
import { frameType, parseInbound } from './protocol.ts'
import type { InboundMessage, OutboundMessage } from './protocol.ts'

export type BridgeStatus = 'connecting' | 'online' | 'offline'

type Listeners = {
  onMessage: (message: InboundMessage) => void
  onStatus: (status: BridgeStatus) => void
}

/** Reconnect delays in ms; the last value repeats forever. */
const BACKOFF_MS = [500, 1_000, 2_000, 4_000, 8_000]

export class BridgeClient {
  private socket: WebSocket | null = null
  private attempt = 0
  private closed = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private currentStatus: BridgeStatus = 'connecting'
  private readonly url: string
  private readonly listeners: Listeners

  constructor(listeners: Listeners) {
    this.listeners = listeners
    this.url = bridgeUrl()
  }

  status(): BridgeStatus {
    return this.currentStatus
  }

  endpoint(): string {
    return this.url
  }

  connect(): void {
    if (this.closed) return
    this.setStatus('connecting')
    console.log(`[bridge] connecting to ${this.url}`)

    let socket: WebSocket
    try {
      socket = new WebSocket(this.url)
    } catch (error) {
      // A malformed URL throws synchronously; treat it like any other failure
      // so the app still boots and shows "bridge offline".
      console.error('[bridge] could not open socket:', error)
      this.scheduleReconnect()
      return
    }
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      this.setStatus('online')
      console.log('[bridge] online')
    }

    socket.onmessage = (event) => {
      if (typeof event.data !== 'string') return
      const message = parseInbound(event.data)
      if (!message) {
        // Not a warning: the bridge is allowed to speak message types this
        // build does not implement, and greeting/keepalive frames are normal.
        console.debug(`[bridge] ignoring frame of type ${frameType(event.data) ?? '(unparseable)'}`)
        return
      }
      this.listeners.onMessage(message)
    }

    socket.onerror = () => {
      // `onclose` always follows, so the reconnect is scheduled there and this
      // handler only exists to stop the error surfacing as unhandled.
      console.warn('[bridge] socket error')
    }

    socket.onclose = () => {
      if (this.socket === socket) this.socket = null
      console.log('[bridge] offline')
      this.scheduleReconnect()
    }
  }

  /** Returns false when the socket is not open, so callers can render an
   *  offline state instead of silently dropping the request. */
  send(message: OutboundMessage): boolean {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.warn(`[bridge] send dropped (${this.currentStatus}): ${message.type}`)
      return false
    }
    this.socket.send(JSON.stringify(message))
    console.log(`[bridge] sent ${message.type}`)
    return true
  }

  /**
   * Send one raw PCM frame. Binary frames are the microphone channel — the
   * bridge reads them as PCM16 LE / 16 kHz / mono and never as JSON — so this
   * deliberately does not log per frame: at 10 frames a second the log would
   * be useless for anything else.
   *
   * Returns false when the frame was dropped, either because the socket is
   * closed or because it is already backed up. Dropping the newest audio beats
   * queueing without bound: a stalled bridge would otherwise eat memory on the
   * phone and deliver a question minutes late.
   */
  sendBinary(pcm: Uint8Array): boolean {
    const socket = this.socket
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    if (socket.bufferedAmount > ASK_MAX_BUFFERED_BYTES) {
      console.warn(`[bridge] dropping audio frame, ${socket.bufferedAmount} bytes still queued`)
      return false
    }
    socket.send(pcm)
    return true
  }

  close(): void {
    this.closed = true
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer)
    this.socket?.close()
    this.socket = null
  }

  private scheduleReconnect(): void {
    if (this.closed || this.reconnectTimer !== null) return
    this.setStatus('offline')
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)]
    this.attempt++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private setStatus(status: BridgeStatus): void {
    if (this.currentStatus === status) return
    this.currentStatus = status
    this.listeners.onStatus(status)
  }
}
