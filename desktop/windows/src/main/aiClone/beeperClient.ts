// Thin client for the Beeper Desktop API — a localhost REST + WebSocket server
// that Beeper Desktop runs on port 23373 (the port documented at
// https://developers.beeper.com/desktop-api; some builds bind 23374 instead, so
// `discoverBeeperBaseUrl` probes both). The user creates an access token in
// Beeper → Settings → Integrations ("Approved connections"); everything stays
// on-device.
import WebSocket from 'ws'

export const BEEPER_BASE_URL = 'http://localhost:23373'
/** Ports Beeper Desktop is known to bind, most-documented first. */
export const BEEPER_CANDIDATE_PORTS = [23373, 23374]
/** A hung (accepted-but-silent) local socket must not stall the reply loop. */
const REQUEST_TIMEOUT_MS = 15_000

/**
 * Find the port the running Beeper Desktop actually listens on. `/v1/info` is
 * public (no token), so this can run before the user has pasted one. Returns
 * the documented default when nothing answers, so callers still report a
 * truthful "unreachable" against a real address.
 */
export async function discoverBeeperBaseUrl(fetchImpl: typeof fetch = fetch): Promise<string> {
  for (const port of BEEPER_CANDIDATE_PORTS) {
    const base = `http://localhost:${port}`
    try {
      const res = await fetchImpl(`${base}/v1/info`, {
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS)
      })
      // Any answer at all (including 401) proves Beeper owns this port.
      if (res.status < 500) return base
    } catch {
      /* nothing listening here — try the next candidate */
    }
  }
  return BEEPER_BASE_URL
}

/** Raw Beeper wire shapes (subset of fields the clone uses). */
export type BeeperChat = {
  id: string
  title?: string
  network?: string
  type?: 'single' | 'group'
  lastActivity?: string | number
  isArchived?: boolean
  isMuted?: boolean
}

export type BeeperMessage = {
  id: string
  chatID?: string
  accountID?: string
  text?: string
  type?: string
  senderID?: string
  senderName?: string
  /** True if the authenticated user sent the message. */
  isSender?: boolean
  timestamp?: string | number
  isDeleted?: boolean
}

/** message.upserted frame from ws://…/v1/ws (subscriptions.set protocol). */
export type BeeperWsEvent = {
  type: string
  chatID?: string
  ids?: string[]
  entries?: BeeperMessage[]
}

export type BeeperResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: 'unreachable' | 'unauthorized' | 'http_error'; detail?: string }

/** Normalize a Beeper timestamp (ISO string or ms epoch) to ms, or undefined. */
export function beeperTimestampMs(ts: string | number | undefined): number | undefined {
  if (ts === undefined || ts === null) return undefined
  if (typeof ts === 'number') return ts
  const parsed = Date.parse(ts)
  return Number.isNaN(parsed) ? undefined : parsed
}

/**
 * Normalize a message page to oldest-first. The API documents message pages
 * only as "sorted by timestamp" without a guaranteed direction, and both the
 * prompt transcript and any replay need oldest-first, so sort explicitly rather
 * than assuming. A page where some message lacks a usable timestamp carries no
 * recoverable order, so it is passed through untouched.
 */
export function oldestFirst(messages: BeeperMessage[]): BeeperMessage[] {
  const stamped = messages.map((m, index) => ({ m, index, ts: beeperTimestampMs(m.timestamp) }))
  if (stamped.some((s) => s.ts === undefined)) return messages
  return stamped
    .sort((a, b) => (a.ts! === b.ts! ? a.index - b.index : a.ts! - b.ts!))
    .map((s) => s.m)
}

/** Pull the item array out of a Beeper list response ({items:[…]} or bare []). */
function listItems<T>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[]
  const items = (body as { items?: T[] })?.items
  return Array.isArray(items) ? items : []
}

export class BeeperClient {
  constructor(
    private token: string,
    private baseUrl: string = BEEPER_BASE_URL
  ) {}

  private async request<T>(
    method: 'GET' | 'POST',
    path: string,
    body?: unknown
  ): Promise<BeeperResult<T>> {
    let res: Response
    try {
      res = await fetch(`${this.baseUrl}${path}`, {
        method,
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        headers: {
          Authorization: `Bearer ${this.token}`,
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {})
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {})
      })
    } catch (e) {
      // Connection refused etc. — Beeper Desktop isn't running.
      return { ok: false, error: 'unreachable', detail: (e as Error).message }
    }
    if (res.status === 401 || res.status === 403) return { ok: false, error: 'unauthorized' }
    if (!res.ok) {
      return { ok: false, error: 'http_error', detail: `HTTP ${res.status} on ${path}` }
    }
    try {
      return { ok: true, value: (await res.json()) as T }
    } catch {
      return { ok: true, value: undefined as T }
    }
  }

  /** Cheap probe used by Connect and by reachability checks. */
  async validateToken(): Promise<BeeperResult<void>> {
    const r = await this.request<unknown>('GET', '/v1/chats')
    return r.ok ? { ok: true, value: undefined } : r
  }

  async listChats(): Promise<BeeperResult<BeeperChat[]>> {
    const r = await this.request<unknown>('GET', '/v1/chats')
    return r.ok ? { ok: true, value: listItems<BeeperChat>(r.value) } : r
  }

  /** Latest messages in a chat; use `oldestFirst` before treating the page as
   *  a transcript (the API does not guarantee a direction). */
  async listMessages(chatID: string): Promise<BeeperResult<BeeperMessage[]>> {
    const r = await this.request<unknown>(
      'GET',
      `/v1/chats/${encodeURIComponent(chatID)}/messages`
    )
    return r.ok ? { ok: true, value: listItems<BeeperMessage>(r.value) } : r
  }

  async sendMessage(
    chatID: string,
    text: string,
    replyToMessageID?: string
  ): Promise<BeeperResult<{ pendingMessageID?: string }>> {
    return this.request('POST', `/v1/chats/${encodeURIComponent(chatID)}/messages`, {
      text,
      ...(replyToMessageID ? { replyToMessageID } : {})
    })
  }

  /**
   * Subscribe to message.upserted events for every chat. Reconnects with capped
   * backoff until closed; `onDown` fires when the socket drops (so the caller
   * can surface "Beeper unreachable" and/or fall back to polling).
   */
  subscribe(handlers: {
    onEvent: (e: BeeperWsEvent) => void
    onUp?: () => void
    onDown?: (reason: string) => void
  }): { close: () => void } {
    let ws: WebSocket | null = null
    let closed = false
    let attempt = 0
    let retryTimer: NodeJS.Timeout | null = null

    const connect = (): void => {
      if (closed) return
      ws = new WebSocket(`${this.baseUrl.replace(/^http/, 'ws')}/v1/ws`, {
        headers: { Authorization: `Bearer ${this.token}` }
      })
      ws.on('open', () => {
        attempt = 0
        ws?.send(JSON.stringify({ type: 'subscriptions.set', requestID: 'r1', chatIDs: ['*'] }))
        handlers.onUp?.()
      })
      ws.on('message', (data) => {
        try {
          const frame = JSON.parse(String(data)) as BeeperWsEvent
          if (frame?.type) handlers.onEvent(frame)
        } catch {
          /* ignore non-JSON frames */
        }
      })
      const scheduleRetry = (reason: string): void => {
        if (closed || retryTimer) return
        handlers.onDown?.(reason)
        const delay = Math.min(30_000, 1_000 * 2 ** attempt++)
        retryTimer = setTimeout(() => {
          retryTimer = null
          connect()
        }, delay)
      }
      ws.on('close', () => scheduleRetry('closed'))
      ws.on('error', (e) => scheduleRetry(e.message))
    }

    connect()
    return {
      close: () => {
        closed = true
        if (retryTimer) clearTimeout(retryTimer)
        try {
          ws?.close()
        } catch {
          /* already closed */
        }
      }
    }
  }
}
