// Local Beeper Desktop REST client. Personal-use only — aggressive auto-send
// can get WhatsApp/Telegram accounts banned, so callers default to draft mode.
export const BEEPER_BASE = 'http://127.0.0.1:23373'
export const BEEPER_DOWNLOAD_URL = 'https://www.beeper.com/download'

const TIMEOUT_MS = 8_000

export class BeeperHttpError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
    this.name = 'BeeperHttpError'
  }
}

export type BeeperAccountRow = {
  network?: string
  status?: string
}

export type BeeperMessage = {
  id: string
  text?: string
  isSender?: boolean
  isDeleted?: boolean
  senderName?: string
}

export type BeeperChat = {
  id: string
  network: string
  type: string
  title: string
  unreadCount: number
  isMuted?: boolean
  preview?: BeeperMessage
}

async function beeperFetch(
  path: string,
  init: { token?: string; method?: string; body?: unknown; timeoutMs?: number }
): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), init.timeoutMs ?? TIMEOUT_MS)
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (init.token) headers.Authorization = `Bearer ${init.token}`
    if (init.body !== undefined) headers['Content-Type'] = 'application/json'
    return await fetch(`${BEEPER_BASE}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: ctrl.signal
    })
  } finally {
    clearTimeout(timer)
  }
}

export async function probeBeeper(): Promise<{ running: boolean }> {
  try {
    await beeperFetch('/v1/info', { timeoutMs: 1_500 })
    return { running: true }
  } catch {
    return { running: false }
  }
}

export async function listAccounts(token: string): Promise<BeeperAccountRow[]> {
  const res = await beeperFetch('/v1/accounts', { token })
  if (!res.ok) throw new BeeperHttpError(res.status, `accounts ${res.status}`)
  const data = (await res.json()) as unknown
  return Array.isArray(data) ? (data as BeeperAccountRow[]) : []
}

export async function listChats(token: string): Promise<BeeperChat[]> {
  const out: BeeperChat[] = []
  let cursor: string | undefined
  for (let page = 0; page < 3; page++) {
    const q = cursor ? `?cursor=${encodeURIComponent(cursor)}&direction=before` : ''
    const res = await beeperFetch(`/v1/chats${q}`, { token })
    if (!res.ok) throw new BeeperHttpError(res.status, `chats ${res.status}`)
    const data = (await res.json()) as {
      items?: BeeperChat[]
      hasMore?: boolean
      oldestCursor?: string
    }
    const items = Array.isArray(data.items) ? data.items : []
    out.push(...items)
    if (!data.hasMore || !data.oldestCursor) break
    cursor = data.oldestCursor
  }
  return out
}

export async function listMessages(token: string, chatId: string): Promise<BeeperMessage[]> {
  const res = await beeperFetch(`/v1/chats/${encodeURIComponent(chatId)}/messages`, { token })
  if (!res.ok) throw new BeeperHttpError(res.status, `messages ${res.status}`)
  const data = (await res.json()) as { items?: BeeperMessage[] }
  return Array.isArray(data.items) ? data.items : []
}

export async function sendMessage(
  token: string,
  chatId: string,
  text: string,
  replyToMessageID?: string
): Promise<void> {
  const body: { text: string; replyToMessageID?: string } = { text }
  if (replyToMessageID) body.replyToMessageID = replyToMessageID
  const res = await beeperFetch(`/v1/chats/${encodeURIComponent(chatId)}/messages`, {
    token,
    method: 'POST',
    body
  })
  if (!res.ok) throw new BeeperHttpError(res.status, `send ${res.status}`)
}

export async function markChatRead(token: string, chatId: string): Promise<void> {
  const res = await beeperFetch(`/v1/chats/${encodeURIComponent(chatId)}/read`, {
    token,
    method: 'POST'
  })
  if (!res.ok) throw new BeeperHttpError(res.status, `read ${res.status}`)
}
