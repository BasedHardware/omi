// Poll Beeper for unread DMs and draft (or auto-send) an Omi-grounded reply.
import { randomUUID } from 'crypto'
import { BrowserWindow, shell } from 'electron'
import type { BeeperAccount, BeeperDraft, BeeperStatus } from '../../shared/types'
import { showBestEffortNotification } from '../notify'
import { recordFallback } from '../observability/fallback'
import { isAllowedExternalScheme } from '../externalUrl'
import { hideBeeperDraftToastIf, showBeeperDraftToast } from '../insight/toastWindow'
import {
  BeeperHttpError,
  BEEPER_DOWNLOAD_URL,
  listAccounts,
  listChats,
  listMessages,
  markChatRead,
  probeBeeper,
  sendMessage
} from './client'
import { generateChatReply } from './omiReply'
import { buildReplyPrompt, sanitizeReplyText, shouldReplyToChat } from './replyLogic'
import { loadBeeperSettings, patchBeeperSettings, type BeeperSettings } from './settings'
import {
  addDraft,
  clearBeeperState,
  getHandledMessageId,
  listDrafts,
  markHandled,
  removeDraft
} from './state'
import { clearBeeperToken, loadBeeperToken, saveBeeperToken } from './tokenStore'

const POLL_MS = 20_000
const MAX_REPLIES_PER_TICK = 3

let timer: ReturnType<typeof setInterval> | null = null
let ticking = false
let lastError: string | undefined
let lastPollAt: number | undefined
let warnedNotRunning = false

function imessageSupported(): boolean {
  return process.platform === 'darwin'
}

export function presentBeeperDraft(draft: BeeperDraft): BeeperDraft {
  const stored = addDraft(draft)
  publish()
  try {
    showBeeperDraftToast(stored)
  } catch (e) {
    console.warn(
      '[beeper] draft toast failed:',
      e instanceof Error ? e.message : 'error'
    )
  }
  return stored
}

function publish(): void {
  const status = currentStatusSync()
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('beeper:changed', status)
  }
}

function connectedAccounts(rows: { network?: string; status?: string }[]): BeeperAccount[] {
  return rows
    .filter((r) => typeof r.network === 'string' && r.network.length > 0)
    .map((r) => ({
      network: r.network as string,
      connected: r.status === 'connected' || r.status === 'backfilling' || r.status === 'connecting'
    }))
}

export function currentStatusSync(running = true): BeeperStatus {
  const settings = loadBeeperSettings()
  const token = loadBeeperToken()
  return {
    running,
    connected: Boolean(token),
    enabled: settings.enabled,
    sendMode: settings.sendMode,
    networks: settings.networks,
    accounts: [],
    draftCount: listDrafts().length,
    imessageSupported: imessageSupported(),
    lastError,
    lastPollAt
  }
}

export async function getStatus(): Promise<BeeperStatus> {
  const probe = await probeBeeper()
  const settings = loadBeeperSettings()
  const token = loadBeeperToken()
  let accounts: BeeperAccount[] = []
  if (probe.running && token) {
    try {
      accounts = connectedAccounts(await listAccounts(token))
    } catch (e) {
      lastError =
        e instanceof BeeperHttpError && e.status === 401 ? 'invalid_token' : 'beeper_error'
    }
  }
  return {
    running: probe.running,
    connected: Boolean(token),
    enabled: settings.enabled,
    sendMode: settings.sendMode,
    networks: settings.networks,
    accounts,
    draftCount: listDrafts().length,
    imessageSupported: imessageSupported(),
    lastError,
    lastPollAt
  }
}

export async function connect(token: string): Promise<BeeperStatus> {
  const trimmed = token.trim()
  if (!trimmed) throw new Error('Paste a Beeper access token')
  const probe = await probeBeeper()
  if (!probe.running) throw new Error('Beeper Desktop is not running')
  await listAccounts(trimmed)
  saveBeeperToken(trimmed)
  lastError = undefined
  syncPoller()
  const status = await getStatus()
  publish()
  return status
}

export async function disconnect(): Promise<BeeperStatus> {
  stopPoller()
  clearBeeperToken()
  clearBeeperState()
  patchBeeperSettings({ enabled: false })
  lastError = undefined
  const status = await getStatus()
  publish()
  return status
}

export async function setSettings(patch: Partial<BeeperSettings>): Promise<BeeperStatus> {
  const networks = patch.networks
    ? imessageSupported()
      ? patch.networks
      : patch.networks.filter((n) => n !== 'imessage')
    : undefined
  patchBeeperSettings({ ...patch, networks })
  syncPoller()
  const status = await getStatus()
  publish()
  return status
}

export function openDownload(): void {
  if (!isAllowedExternalScheme(BEEPER_DOWNLOAD_URL, ['https'])) return
  void shell.openExternal(BEEPER_DOWNLOAD_URL)
}

export function syncPoller(): void {
  const settings = loadBeeperSettings()
  const token = loadBeeperToken()
  if (settings.enabled && token) startPoller()
  else stopPoller()
}

function startPoller(): void {
  if (timer) return
  timer = setInterval(() => {
    void tick().catch((e) => {
      console.warn('[beeper] poll failed:', e instanceof Error ? e.message : 'error')
    })
  }, POLL_MS)
  void tick().catch(() => {})
}

function stopPoller(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

export async function pollNow(): Promise<BeeperStatus> {
  await tick()
  return getStatus()
}

export async function sendDraft(id: string): Promise<BeeperStatus> {
  hideBeeperDraftToastIf(id)
  const draft = removeDraft(id)
  if (!draft) return getStatus()
  const token = loadBeeperToken()
  if (!token) throw new Error('Beeper is not connected')
  await sendMessage(token, draft.chatId, draft.replyText, draft.inboundMessageId)
  try {
    await markChatRead(token, draft.chatId)
  } catch {
    /* send already happened */
  }
  publish()
  return getStatus()
}

export async function dismissDraft(id: string): Promise<BeeperStatus> {
  hideBeeperDraftToastIf(id)
  removeDraft(id)
  publish()
  return getStatus()
}

async function tick(): Promise<void> {
  if (ticking) return
  const settings = loadBeeperSettings()
  const token = loadBeeperToken()
  if (!settings.enabled || !token) return
  ticking = true
  try {
    const probe = await probeBeeper()
    if (!probe.running) {
      if (!warnedNotRunning) {
        warnedNotRunning = true
        lastError = 'beeper_not_running'
        recordFallback({
          component: 'other',
          from: 'beeper_poll',
          to: 'skipped',
          reason: 'other',
          outcome: 'degraded'
        })
        publish()
      }
      return
    }
    warnedNotRunning = false

    const chats = await listChats(token)
    let replies = 0
    for (const chat of chats) {
      if (replies >= MAX_REPLIES_PER_TICK) break
      const decision = shouldReplyToChat(chat, {
        enabledNetworks: settings.networks,
        handledMessageId: getHandledMessageId(chat.id)
      })
      if (!decision.ok) continue

      let history: { isSender: boolean; text: string }[] = []
      try {
        const messages = await listMessages(token, chat.id)
        history = messages
          .filter((m) => typeof m.text === 'string' && m.text.trim() && !m.isDeleted)
          .map((m) => ({ isSender: m.isSender === true, text: m.text as string }))
      } catch {
        history = [{ isSender: false, text: decision.inboundText }]
      }

      const prompt = buildReplyPrompt({
        network: chat.network,
        chatTitle: chat.title || 'them',
        inboundText: decision.inboundText,
        history
      })
      let reply: string | null
      try {
        reply = sanitizeReplyText(await generateChatReply(prompt))
      } catch (e) {
        lastError = 'omi_reply_failed'
        recordFallback({
          component: 'other',
          from: 'beeper_reply',
          to: 'skipped',
          reason: 'other',
          outcome: 'degraded'
        })
        console.warn('[beeper] reply generation failed:', e instanceof Error ? e.message : 'error')
        continue
      }
      if (!reply) continue

      if (settings.sendMode === 'auto') {
        try {
          await sendMessage(token, chat.id, reply, decision.inboundMessageId)
          await markChatRead(token, chat.id).catch(() => {})
          markHandled(chat.id, decision.inboundMessageId)
        } catch {
          presentBeeperDraft({
            id: randomUUID(),
            chatId: chat.id,
            chatTitle: chat.title || 'Chat',
            network: chat.network,
            inboundText: decision.inboundText,
            replyText: reply,
            inboundMessageId: decision.inboundMessageId,
            createdAt: Date.now()
          })
          lastError = 'send_failed_drafted'
          recordFallback({
            component: 'other',
            from: 'auto_send',
            to: 'draft',
            reason: 'other',
            outcome: 'degraded'
          })
          showBestEffortNotification(
            `Reply for ${chat.title || 'a chat'}`,
            'Could not send — saved as a draft in Settings'
          )
        }
      } else {
        presentBeeperDraft({
          id: randomUUID(),
          chatId: chat.id,
          chatTitle: chat.title || 'Chat',
          network: chat.network,
          inboundText: decision.inboundText,
          replyText: reply,
          inboundMessageId: decision.inboundMessageId,
          createdAt: Date.now()
        })
        showBestEffortNotification(`Reply for ${chat.title || 'a chat'}`, reply)
      }
      replies += 1
    }
    lastError = undefined
    lastPollAt = Date.now()
    if (replies > 0) publish()
  } catch (e) {
    lastError = e instanceof BeeperHttpError && e.status === 401 ? 'invalid_token' : 'beeper_error'
    console.warn('[beeper] tick failed:', e instanceof Error ? e.message : 'error')
  } finally {
    ticking = false
  }
}
