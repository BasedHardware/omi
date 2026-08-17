/**
 * Wearable listen lane: streams decoded device PCM into the same /v4/listen
 * session the microphone uses, so a conversation captured on the pendant is
 * indistinguishable from one captured on the laptop.
 *
 * Two constraints shape this driver:
 *  - Only one conversation socket per user is safe (two coalesce through a
 *    racy server-side pointer), so the lane refuses to open while the
 *    continuous microphone session holds the slot.
 *  - The device window feeds audio itself, so unlike the microphone path it
 *    never issues an audio-start capture command; it opens the session and
 *    pushes PCM straight in.
 *
 * Reconnects reuse the shared backoff kit and resume the same conversation
 * through clientConversationId; when reconnects are exhausted the retained
 * segments are handed back so the caller can rescue the conversation locally.
 */

import type { BackendSegment, ListenEvent } from '../../../../shared/types'
import {
  MAX_RECONNECT_ATTEMPTS,
  createSegmentRetainer,
  isRateLimitedDropError,
  isRetryableDropError,
  reconnectDelayJitteredMs,
  type SegmentRetainer
} from '../../capture/liveRescue'

export type DeviceLaneState =
  | 'idle'
  | 'blocked'
  | 'connecting'
  | 'streaming'
  | 'reconnecting'
  | 'stopped'

export interface DeviceLaneCallbacks {
  onSegments?: (segments: BackendSegment[]) => void
  onEvent?: (event: ListenEvent) => void
  onStateChange?: (state: DeviceLaneState) => void
  /** Reconnects are exhausted: the caller saves what was transcribed. */
  onRescue?: (segments: BackendSegment[]) => void
  onError?: (error: Error) => void
}

export interface DeviceLaneTransport {
  /** True when another window already holds the conversation socket. */
  isConversationLaneBusy: () => Promise<boolean>
  startSession: (args: { sessionId: string; clientConversationId: string }) => Promise<void>
  feed: (sessionId: string, pcm: ArrayBuffer) => void
  stopSession: (sessionId: string) => void
  /** Subscribes to backend messages for this session; returns unsubscribe. */
  subscribe: (handlers: {
    onConnected: (sessionId: string) => void
    onSegments: (sessionId: string, segments: BackendSegment[]) => void
    onEvent: (sessionId: string, event: ListenEvent) => void
    onClosed: (sessionId: string, code: number, reason: string) => void
    onError: (sessionId: string, message: string) => void
  }) => () => void
  /** Injectable so tests drive backoff without real waiting. */
  sleep: (ms: number, signal: AbortSignal) => Promise<'elapsed' | 'aborted'>
  newSessionId: () => string
  newConversationId: () => string
}

export class DeviceListenSession {
  private state: DeviceLaneState = 'idle'
  private sessionId: string | null = null
  private conversationId: string | null = null
  private unsubscribe: (() => void) | null = null
  private retainer: SegmentRetainer = createSegmentRetainer()
  private reconnectAttempt = 0
  private abort = new AbortController()
  private stopped = false

  constructor(
    private readonly transport: DeviceLaneTransport,
    private readonly callbacks: DeviceLaneCallbacks = {}
  ) {}

  get currentState(): DeviceLaneState {
    return this.state
  }

  get currentSessionId(): string | null {
    return this.sessionId
  }

  /** Opens the lane. Returns false when the conversation slot is taken. */
  async start(): Promise<boolean> {
    if (this.state !== 'idle' && this.state !== 'stopped') return false
    this.stopped = false
    this.abort = new AbortController()
    this.retainer = createSegmentRetainer()
    this.reconnectAttempt = 0
    this.conversationId = this.transport.newConversationId()

    if (await this.transport.isConversationLaneBusy()) {
      // The microphone lane owns the only safe conversation socket.
      this.setState('blocked')
      return false
    }
    return this.openSession()
  }

  private async openSession(): Promise<boolean> {
    if (this.stopped) return false
    this.setState(this.reconnectAttempt === 0 ? 'connecting' : 'reconnecting')
    const sessionId = this.transport.newSessionId()
    this.sessionId = sessionId

    this.unsubscribe?.()
    this.unsubscribe = this.transport.subscribe({
      onConnected: (id) => {
        if (id !== this.sessionId) return
        this.reconnectAttempt = 0
        this.setState('streaming')
      },
      onSegments: (id, segments) => {
        if (id !== this.sessionId) return
        this.retainer.add(segments)
        this.callbacks.onSegments?.(segments)
      },
      onEvent: (id, event) => {
        if (id !== this.sessionId) return
        this.callbacks.onEvent?.(event)
      },
      onClosed: (id, code, reason) => {
        if (id !== this.sessionId) return
        this.handleDrop(reason || `socket closed (${code})`)
      },
      onError: (id, message) => {
        if (id !== this.sessionId) return
        this.callbacks.onError?.(new Error(message))
        this.handleDrop(message)
      }
    })

    try {
      await this.transport.startSession({
        sessionId,
        clientConversationId: this.conversationId ?? sessionId
      })
      return true
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      this.callbacks.onError?.(new Error(message))
      this.handleDrop(message)
      return false
    }
  }

  /** Feeds decoded PCM. Silently ignored unless the socket is live. */
  feed(pcm: Int16Array): void {
    if (this.state !== 'streaming' && this.state !== 'connecting') return
    const sessionId = this.sessionId
    if (sessionId === null) return
    // Copy out of the decoder's buffer: the frame is reused downstream.
    const copy = new Int16Array(pcm)
    this.transport.feed(sessionId, copy.buffer)
  }

  private handleDrop(reason: string): void {
    if (this.stopped) return
    const sessionId = this.sessionId
    this.sessionId = null
    if (sessionId !== null) this.transport.stopSession(sessionId)

    if (!isRetryableDropError(reason)) {
      // Quota and entitlement closes will not succeed on retry.
      this.finishWithRescue()
      return
    }
    if (this.reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
      this.finishWithRescue()
      return
    }

    this.reconnectAttempt += 1
    const delay = reconnectDelayJitteredMs(this.reconnectAttempt, {
      rateLimited: isRateLimitedDropError(reason)
    })
    this.setState('reconnecting')
    void (async () => {
      const outcome = await this.transport.sleep(delay, this.abort.signal)
      if (outcome !== 'elapsed' || this.stopped) return
      await this.openSession()
    })()
  }

  private finishWithRescue(): void {
    const segments = this.retainer.list()
    this.teardown('stopped')
    if (segments.length > 0) this.callbacks.onRescue?.(segments)
  }

  stop(): void {
    if (this.stopped) return
    this.teardown('stopped')
  }

  private teardown(state: DeviceLaneState): void {
    this.stopped = true
    this.abort.abort()
    const sessionId = this.sessionId
    this.sessionId = null
    this.unsubscribe?.()
    this.unsubscribe = null
    if (sessionId !== null) this.transport.stopSession(sessionId)
    this.setState(state)
  }

  /** Segments retained so far, for a caller-driven rescue. */
  retainedSegments(): BackendSegment[] {
    return this.retainer.list()
  }

  private setState(state: DeviceLaneState): void {
    if (this.state === state) return
    this.state = state
    this.callbacks.onStateChange?.(state)
  }
}
