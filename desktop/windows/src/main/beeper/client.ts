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
  accountID?: string
  network?: string
  status?: string
  bridge?: { type?: string }
}

export type BeeperMessage = {
  id: string
  text?: string
  isSender?: boolean
  isDeleted?: boolean
  isHidden?: boolean
  senderName?: string
  timestamp?: string
}

export type BeeperChat = {
  id: string
  network: string
  type: string
  title: string
  unreadCount: number
  isMuted?: boolean
  lastActivity?: string
  preview?: BeeperMessage
}

export type BeeperChatSearchParams = {
  query?: string
  scope?: 'titles' | 'participants'
  accountIDs?: string[]
  type?: 'single' | 'group' | 'any'
  unreadOnly?: boolean
  limit?: number
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

function chatSearchQuery(params: BeeperChatSearchParams): string {
  const u = new URLSearchParams()
  if (params.query) u.set('query', params.query)
  if (params.scope) u.set('scope', params.scope)
  if (params.type) u.set('type', params.type)
  if (params.unreadOnly) u.set('unreadOnly', 'true')
  if (params.limit != null) u.set('limit', String(params.limit))
  for (const id of params.accountIDs ?? []) {
    if (id) u.append('accountIDs', id)
  }
  const s = u.toString()
  return s ? `?${s}` : ''
}

export async function searchChats(
  token: string,
  params: BeeperChatSearchParams = {}
): Promise<BeeperChat[]> {
  const res = await beeperFetch(`/v1/chats/search${chatSearchQuery(params)}`, {
    token,
    timeoutMs: 12_000
  })
  if (!res.ok) throw new BeeperHttpError(res.status, `chats/search ${res.status}`)
  const data = (await res.json()) as { items?: BeeperChat[] }
  return Array.isArray(data.items) ? data.items : []
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

export async function getChat(token: string, chatId: string): Promise<BeeperChat | null> {
  const res = await beeperFetch(`/v1/chats/${encodeURIComponent(chatId)}`, { token })
  if (res.status === 404) return null
  if (!res.ok) throw new BeeperHttpError(res.status, `chat ${res.status}`)
  const data = (await res.json()) as unknown
  if (!data || typeof data !== 'object') return null
  const row = data as Partial<BeeperChat>
  if (typeof row.id !== 'string' || !row.id) return null
  return {
    id: row.id,
    network: typeof row.network === 'string' ? row.network : '',
    type: typeof row.type === 'string' ? row.type : 'single',
    title: typeof row.title === 'string' ? row.title : 'Chat',
    unreadCount: typeof row.unreadCount === 'number' ? row.unreadCount : 0,
    isMuted: row.isMuted,
    lastActivity: row.lastActivity,
    preview: row.preview
  }
}

export async function listMessages(
  token: string,
  chatId: string,
  opts?: { limit?: number }
): Promise<BeeperMessage[]> {
  const res = await beeperFetch(`/v1/chats/${encodeURIComponent(chatId)}/messages`, {
    token,
    timeoutMs: 12_000
  })
  if (!res.ok) throw new BeeperHttpError(res.status, `messages ${res.status}`)
  const data = (await res.json()) as { items?: BeeperMessage[] }
  const items = Array.isArray(data.items) ? data.items : []
  const cap = opts?.limit
  if (cap == null || items.length <= cap) return items
  const sorted = [...items].sort((a, b) => {
    const ta = Date.parse(a.timestamp ?? '')
    const tb = Date.parse(b.timestamp ?? '')
    const na = Number.isFinite(ta) ? ta : 0
    const nb = Number.isFinite(tb) ? tb : 0
    return na - nb
  })
  return sorted.slice(-cap)
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
