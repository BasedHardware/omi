// Chat + voice Beeper tools. The draft poller (replyService) only watches unread
// WhatsApp/Telegram DMs; these executors let Omi read ANY connected Beeper
// network (LinkedIn, Telegram, WhatsApp, …) on demand and show a Send/Skip
// reply card (draft_beeper_reply).
//
// Impure edges (token store, local Beeper HTTP) are injected so vitest never
// loads Electron. Production binds them with call-time dynamic import.

import { randomUUID } from 'crypto'
import type { ProductToolExecutor } from '../agentKernel/toolRelayBridge'
import type { BeeperDraft } from '../../shared/types'
import { BeeperHttpError, type BeeperAccountRow, type BeeperChat, type BeeperMessage } from './client'
import { buildReplyPrompt, latestInboundMessage, sanitizeReplyText } from './replyLogic'

const CONNECT_HINT =
  'Beeper is not connected in Omi. Open Connect → WhatsApp & Telegram, paste a token from Beeper Settings → Integrations (Allow connections, then Approved connections → +).'

const NOT_RUNNING = 'Beeper Desktop is not running. Open Beeper, then try again.'

export type BeeperChatToolDeps = {
  probe: () => Promise<{ running: boolean }>
  loadToken: () => Promise<string | null>
  listAccounts: (token: string) => Promise<BeeperAccountRow[]>
  searchChats: (
    token: string,
    params: {
      query?: string
      scope?: 'titles' | 'participants'
      accountIDs?: string[]
      type?: 'single' | 'group' | 'any'
      unreadOnly?: boolean
      limit?: number
    }
  ) => Promise<BeeperChat[]>
  listMessages: (
    token: string,
    chatId: string,
    opts?: { limit?: number }
  ) => Promise<BeeperMessage[]>
}

export type BeeperDraftToolDeps = BeeperChatToolDeps & {
  getChat: (token: string, chatId: string) => Promise<BeeperChat | null>
  generateReply: (prompt: string) => Promise<string>
  presentDraft: (draft: BeeperDraft) => Promise<BeeperDraft> | BeeperDraft
  newId: () => string
  now: () => number
}

function stringArg(input: Record<string, unknown>, key: string): string {
  const v = input[key]
  return typeof v === 'string' ? v.trim() : ''
}

function intArg(value: unknown, def: number, min: number, max: number): number {
  let n: number | null = null
  if (typeof value === 'number' && Number.isFinite(value)) n = Math.trunc(value)
  else if (typeof value === 'string') {
    const parsed = Number(value.trim())
    if (Number.isFinite(parsed)) n = Math.trunc(parsed)
  }
  return Math.min(Math.max(n ?? def, min), max)
}

function bindDeps(deps?: Partial<BeeperChatToolDeps>): BeeperChatToolDeps {
  return {
    probe:
      deps?.probe ?? (async () => (await import('./client')).probeBeeper()),
    loadToken:
      deps?.loadToken ?? (async () => (await import('./tokenStore')).loadBeeperToken()),
    listAccounts:
      deps?.listAccounts ?? (async (token) => (await import('./client')).listAccounts(token)),
    searchChats:
      deps?.searchChats ??
      (async (token, params) => (await import('./client')).searchChats(token, params)),
    listMessages:
      deps?.listMessages ??
      (async (token, chatId, opts) => (await import('./client')).listMessages(token, chatId, opts))
  }
}

function bindDraftDeps(deps?: Partial<BeeperDraftToolDeps>): BeeperDraftToolDeps {
  const base = bindDeps(deps)
  return {
    ...base,
    getChat:
      deps?.getChat ?? (async (token, chatId) => (await import('./client')).getChat(token, chatId)),
    generateReply:
      deps?.generateReply ??
      (async (prompt) => (await import('./omiReply')).generateChatReply(prompt)),
    presentDraft:
      deps?.presentDraft ??
      (async (draft) => (await import('./replyService')).presentBeeperDraft(draft)),
    newId: deps?.newId ?? (() => randomUUID()),
    now: deps?.now ?? (() => Date.now())
  }
}

export function matchBeeperAccounts(
  accounts: BeeperAccountRow[],
  networkQuery: string
): BeeperAccountRow[] {
  const q = networkQuery.trim().toLowerCase()
  if (!q) return []
  return accounts.filter((a) => {
    const network = (a.network ?? '').toLowerCase()
    const id = (a.accountID ?? '').toLowerCase()
    const bridge = (a.bridge?.type ?? '').toLowerCase()
    return network.includes(q) || id.includes(q) || bridge.includes(q)
  })
}

export function connectedNetworkLabels(accounts: BeeperAccountRow[]): string {
  const names = accounts
    .filter((a) => a.status === 'connected' || a.status === 'backfilling' || a.status === 'connecting')
    .map((a) => a.network || a.accountID || 'unknown')
  return names.length > 0 ? names.join(', ') : 'none'
}

function formatWhen(iso?: string): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return iso
  try {
    return new Date(t).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

export function formatBeeperChats(chats: BeeperChat[]): string {
  if (chats.length === 0) return 'No matching Beeper chats.'
  const lines = [`Found ${chats.length} Beeper chat(s):`]
  chats.forEach((chat, i) => {
    const unread = chat.unreadCount > 0 ? `, unread ${chat.unreadCount}` : ''
    const when = chat.lastActivity ? `, last ${formatWhen(chat.lastActivity)}` : ''
    const preview = chat.preview?.text?.replace(/\s+/g, ' ').trim().slice(0, 120)
    lines.push(
      `${i + 1}. [${chat.network || 'chat'}] ${chat.title} (${chat.type}, chat_id: ${chat.id}${unread}${when})`
    )
    if (preview) lines.push(`   Preview: ${preview}`)
  })
  lines.push(
    'Use get_beeper_messages with a chat_id to read the thread, then draft_beeper_reply so a Send/Skip card appears on screen.'
  )
  return lines.join('\n')
}

export function formatBeeperMessages(chatId: string, messages: BeeperMessage[]): string {
  const visible = messages.filter((m) => !m.isDeleted && !m.isHidden)
  if (visible.length === 0) return `No messages in chat ${chatId}.`
  const lines = [`Latest ${visible.length} message(s) in ${chatId}:`]
  for (const m of visible) {
    const who = m.isSender ? 'You' : m.senderName || 'Them'
    const when = formatWhen(m.timestamp)
    const prefix = when ? `[${when}] ${who}` : who
    const text = (m.text ?? '').replace(/\s+/g, ' ').trim().slice(0, 500)
    lines.push(`${prefix}: ${text || '(no text)'}`)
  }
  return lines.join('\n')
}

async function requireAccess(
  d: BeeperChatToolDeps
): Promise<{ token: string } | { error: string }> {
  const probe = await d.probe()
  if (!probe.running) return { error: `Error: ${NOT_RUNNING}` }
  const token = await d.loadToken()
  if (!token) return { error: `Error: ${CONNECT_HINT}` }
  return { token }
}

function beeperErrorMessage(e: unknown): string {
  if (e instanceof BeeperHttpError && e.status === 401) {
    return `Error: Beeper rejected the token. Create a new one in Settings → Integrations → Approved connections.`
  }
  if (e instanceof BeeperHttpError) {
    return `Error: Beeper returned ${e.status}.`
  }
  return `Error: Could not reach Beeper Desktop. Is it running?`
}

export function createSearchBeeperChatsExecutor(
  deps?: Partial<BeeperChatToolDeps>
): ProductToolExecutor {
  const d = bindDeps(deps)
  return async (input, ctx) => {
    const access = await requireAccess(d)
    if ('error' in access) return access.error
    if (ctx.signal.aborted) return 'Error: cancelled'
    const query = stringArg(input, 'query')
    const network = stringArg(input, 'network')
    const unreadOnly = input.unread_only === true
    const limit = intArg(input.limit, 15, 1, 30)
    try {
      let accountIDs: string[] | undefined
      if (network) {
        const accounts = await d.listAccounts(access.token)
        if (ctx.signal.aborted) return 'Error: cancelled'
        const matched = matchBeeperAccounts(accounts, network)
        if (matched.length === 0) {
          return `Error: No connected Beeper account matching "${network}". Connected: ${connectedNetworkLabels(accounts)}.`
        }
        accountIDs = matched.map((a) => a.accountID).filter((id): id is string => Boolean(id))
        if (accountIDs.length === 0) {
          return `Error: Beeper account "${network}" has no account id.`
        }
      }
      const chats = await d.searchChats(access.token, {
        query: query || undefined,
        accountIDs,
        unreadOnly: unreadOnly || undefined,
        type: query ? 'any' : 'single',
        limit
      })
      if (ctx.signal.aborted) return 'Error: cancelled'
      return formatBeeperChats(chats)
    } catch (e) {
      return beeperErrorMessage(e)
    }
  }
}

export function createGetBeeperMessagesExecutor(
  deps?: Partial<BeeperChatToolDeps>
): ProductToolExecutor {
  const d = bindDeps(deps)
  return async (input, ctx) => {
    const chatId = stringArg(input, 'chat_id')
    if (!chatId) return 'Error: chat_id is required — call search_beeper_chats first'
    const access = await requireAccess(d)
    if ('error' in access) return access.error
    if (ctx.signal.aborted) return 'Error: cancelled'
    const limit = intArg(input.limit, 20, 1, 40)
    try {
      const messages = await d.listMessages(access.token, chatId, { limit })
      if (ctx.signal.aborted) return 'Error: cancelled'
      return formatBeeperMessages(chatId, messages)
    } catch (e) {
      return beeperErrorMessage(e)
    }
  }
}

export function createDraftBeeperReplyExecutor(
  deps?: Partial<BeeperDraftToolDeps>
): ProductToolExecutor {
  const d = bindDraftDeps(deps)
  return async (input, ctx) => {
    const chatId = stringArg(input, 'chat_id')
    if (!chatId) return 'Error: chat_id is required — call search_beeper_chats first'
    const access = await requireAccess(d)
    if ('error' in access) return access.error
    if (ctx.signal.aborted) return 'Error: cancelled'
    try {
      const [messages, chat] = await Promise.all([
        d.listMessages(access.token, chatId, { limit: 20 }),
        d.getChat(access.token, chatId).catch(() => null)
      ])
      if (ctx.signal.aborted) return 'Error: cancelled'
      const inbound = latestInboundMessage(messages)
      if (!inbound) {
        return 'Error: No inbound message to reply to in this chat.'
      }
      const chatTitle =
        stringArg(input, 'chat_title') || chat?.title || 'them'
      const network = stringArg(input, 'network') || chat?.network || 'chat'
      const history = messages
        .filter((m) => typeof m.text === 'string' && m.text.trim() && !m.isDeleted && !m.isHidden)
        .map((m) => ({ isSender: m.isSender === true, text: m.text as string }))
      const prompt = buildReplyPrompt({
        network,
        chatTitle,
        inboundText: inbound.text,
        history
      })
      let raw: string
      try {
        raw = await d.generateReply(prompt)
      } catch {
        return 'Error: Could not draft a reply from memories.'
      }
      if (ctx.signal.aborted) return 'Error: cancelled'
      const reply = sanitizeReplyText(raw)
      if (!reply) return 'Error: Could not draft a reply from memories.'
      const stored = await d.presentDraft({
        id: d.newId(),
        chatId,
        chatTitle,
        network,
        inboundText: inbound.text,
        replyText: reply,
        inboundMessageId: inbound.id,
        createdAt: d.now()
      })
      return [
        `Drafted a reply for ${stored.chatTitle} on ${stored.network}.`,
        'A Send/Skip card is on screen — the user taps Send. Never send it yourself.',
        'Speak that the draft is on the card. Do not read the draft aloud unless asked.',
        '',
        `Their last message: ${stored.inboundText}`,
        `Suggested reply: ${stored.replyText}`
      ].join('\n')
    } catch (e) {
      return beeperErrorMessage(e)
    }
  }
}
