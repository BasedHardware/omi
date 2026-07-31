// Track 2 (AI clone) — IPC surface + the background poll loop that ties the
// pure modules in main/aiClone/ together with the real Beeper Desktop API.
//
// Flow for an opted-in chat:
//   poll (setInterval) → beeperClient.listRecentMessages → chatMonitor picks
//   new inbound messages → for each, broadcast an event with a built prompt →
//   renderer calls its authenticated LLM path and hands the draft back via
//   aiCloneSubmitDraft → autoReplyPolicy decides send / queue / skip →
//   beeperClient.sendMessage or draftStore, respectively.
//
// The renderer — not main — makes the actual model call (see
// personaDraftPrompt.ts's header comment): main only assembles context and
// applies the safety/send policy, so the credentialed call stays where the
// rest of typed chat already makes it (useChat.ts's callAgentLLM).

import { ipcMain, BrowserWindow } from 'electron'
import {
  createBeeperClient,
  type BeeperClient,
  type BeeperMessageSummary
} from '../aiClone/beeperClient'
import { BeeperTokenStore } from '../aiClone/beeperTokenStore'
import { ChatSettingsStore } from '../aiClone/chatSettingsStore'
import { DraftStore } from '../aiClone/draftStore'
import { selectNewInboundMessages, type BeeperMessageLike } from '../aiClone/chatMonitor'
import { decideReplyAction, looksSensitive } from '../aiClone/autoReplyPolicy'
import {
  buildDraftPrompt,
  draftNeedsInput,
  type DraftContextMessage
} from '../aiClone/personaDraftPrompt'
import { getLatestProfileText } from '../assistants/aiUserProfile/service'
import type {
  AiCloneChatMode,
  AiCloneChatSummary,
  AiCloneIncomingMessageEvent,
  AiClonePendingDraft,
  AiCloneStatus,
  AiCloneSubmitDraftArgs,
  AiCloneSubmitDraftResult
} from '../../shared/types'

const POLL_INTERVAL_MS = 60_000
/** How many prior messages from the same fetch to include as tone/continuity
 *  context — deliberately small, see personaDraftPrompt.ts. */
const HISTORY_WINDOW = 6

// Lazy singletons: constructing these calls Electron's app.getPath(), which
// must not happen merely from importing this module (before app is ready, or
// — in tests — before a temp userData dir mock is in place).
let _tokenStore: BeeperTokenStore | null = null
function tokenStore(): BeeperTokenStore {
  if (!_tokenStore) _tokenStore = new BeeperTokenStore()
  return _tokenStore
}
let _chatSettings: ChatSettingsStore | null = null
function chatSettings(): ChatSettingsStore {
  if (!_chatSettings) _chatSettings = new ChatSettingsStore()
  return _chatSettings
}
let _drafts: DraftStore | null = null
function drafts(): DraftStore {
  if (!_drafts) _drafts = new DraftStore()
  return _drafts
}

function messageText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function broadcast(channel: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send(channel, payload)
  }
}

// One client cached per stored token so a poll tick doesn't reconstruct the
// SDK client every time; invalidated on connect/disconnect since the token
// (the only thing the client is keyed on) just changed.
let cachedClient: { token: string; client: BeeperClient } | null = null

function clientOrNull(): BeeperClient | null {
  const token = tokenStore().get()
  if (!token) return null
  if (cachedClient?.token !== token) cachedClient = { token, client: createBeeperClient(token) }
  return cachedClient.client
}

function toMessageLike(message: BeeperMessageSummary): BeeperMessageLike {
  return {
    id: message.id,
    isSender: message.isSender,
    timestamp: message.timestamp,
    text: message.text
  }
}

async function statusFor(client: BeeperClient | null): Promise<AiCloneStatus> {
  if (!client) return { connected: false, accounts: [] }
  try {
    const accounts = await client.verifyConnection()
    return { connected: true, accounts }
  } catch (error) {
    return { connected: false, accounts: [], error: messageText(error) }
  }
}

/** One poll pass over every opted-in chat. Exported for the interval below
 *  and for a manual "check now" if a future UI wants one; errors on a single
 *  chat never abort the rest of the cycle. */
export async function pollAiCloneChats(client: BeeperClient = clientOrNull()!): Promise<void> {
  const chatsToCheck = chatSettings()
    .list()
    .filter((c) => c.mode !== 'off')
  for (const setting of chatsToCheck) {
    try {
      const recent = await client.listRecentMessages(setting.chatID)
      const ascending = [...recent].sort((a, b) => a.timestamp - b.timestamp)
      const { newMessages, latestTimestamp } = selectNewInboundMessages(
        ascending.map(toMessageLike),
        setting.lastSeenTimestamp
      )
      if (latestTimestamp !== undefined) chatSettings().setCursor(setting.chatID, latestTimestamp)

      for (const incoming of newMessages) {
        const index = ascending.findIndex((m) => m.id === incoming.id)
        const historyMessages = (index >= 0 ? ascending.slice(0, index) : []).slice(-HISTORY_WINDOW)
        const history: DraftContextMessage[] = historyMessages
          .filter((m) => typeof m.text === 'string' && m.text.trim().length > 0)
          .map((m) => ({
            senderName: setting.displayName,
            text: m.text as string,
            isSelf: m.isSender
          }))

        const prompt = buildDraftPrompt({
          personaProfileText: getLatestProfileText(),
          chatDisplayName: setting.displayName,
          history,
          incomingMessage: {
            senderName: setting.displayName,
            text: incoming.text ?? '',
            isSelf: false
          }
        })
        // Renderer's callAgentLLM takes a single prompt string, not a
        // messages array — fold the system turn into the one user turn it
        // sends rather than duplicating a chat-completions client here.
        const promptText = prompt.map((m) => m.content).join('\n\n')

        const event: AiCloneIncomingMessageEvent = {
          chatID: setting.chatID,
          chatDisplayName: setting.displayName,
          mode: setting.mode,
          incomingMessageText: incoming.text ?? '',
          promptText
        }
        broadcast('aiClone:incomingMessage', event)
      }
    } catch (error) {
      console.log(`[aiClone] poll failed for chat ${setting.chatID}: ${messageText(error)}`)
    }
  }
}

let pollTimer: NodeJS.Timeout | null = null

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    const client = clientOrNull()
    if (!client) return
    void pollAiCloneChats(client)
  }, POLL_INTERVAL_MS)
  // Don't hold the process open just for this timer (mirrors other
  // best-effort background intervals in this codebase).
  pollTimer.unref?.()
}

export function stopAiClonePolling(): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

async function resolveDraftSend(chatID: string, text: string): Promise<void> {
  const client = clientOrNull()
  if (!client) throw new Error('Beeper is not connected.')
  await client.sendMessage(chatID, text)
}

export function registerAiCloneHandlers(): void {
  ipcMain.handle('aiClone:connect', async (_e, accessToken: string): Promise<AiCloneStatus> => {
    const probe = createBeeperClient(accessToken)
    const status = await statusFor(probe)
    if (status.connected) {
      tokenStore().set(accessToken)
      cachedClient = { token: accessToken, client: probe }
      startPolling()
    }
    return status
  })

  ipcMain.handle('aiClone:status', (): Promise<AiCloneStatus> => statusFor(clientOrNull()))

  ipcMain.handle('aiClone:disconnect', (): void => {
    tokenStore().clear()
    cachedClient = null
    stopAiClonePolling()
  })

  ipcMain.handle('aiClone:listChats', async (): Promise<AiCloneChatSummary[]> => {
    const client = clientOrNull()
    if (!client) return []
    const chats = await client.listChats()
    return chats.map((chat) => {
      const saved = chatSettings().get(chat.chatID)
      return {
        chatID: chat.chatID,
        displayName: chat.displayName,
        network: chat.network,
        type: chat.type,
        mode: saved?.mode ?? 'off'
      }
    })
  })

  ipcMain.handle(
    'aiClone:setChatMode',
    (_e, chatID: string, displayName: string, mode: AiCloneChatMode): void => {
      chatSettings().upsert({ chatID, displayName, mode })
    }
  )

  ipcMain.handle('aiClone:listDrafts', (): AiClonePendingDraft[] => drafts().list())

  ipcMain.handle(
    'aiClone:approveDraft',
    async (_e, id: string, editedText?: string): Promise<void> => {
      const draft = drafts().get(id)
      if (!draft) return
      await resolveDraftSend(draft.chatID, editedText?.trim() || draft.draftText)
      drafts().remove(id)
    }
  )

  ipcMain.handle('aiClone:dismissDraft', (_e, id: string): void => {
    drafts().remove(id)
  })

  ipcMain.handle(
    'aiClone:submitDraft',
    async (_e, args: AiCloneSubmitDraftArgs): Promise<AiCloneSubmitDraftResult> => {
      const setting = chatSettings().get(args.chatID)
      const mode = setting?.mode ?? 'off'
      const decision = decideReplyAction({
        mode,
        draftText: args.draftText,
        needsInput: draftNeedsInput(args.draftText)
      })

      if (decision === 'skip') return { action: 'skipped' }

      if (decision === 'send') {
        await resolveDraftSend(args.chatID, args.draftText)
        return { action: 'sent' }
      }

      // 'queue_for_review'
      const draft = drafts().add({
        chatID: args.chatID,
        chatDisplayName: args.chatDisplayName,
        incomingMessageText: args.incomingMessageText,
        draftText: args.draftText
      })
      return { action: 'queued_for_review', draft }
    }
  )

  if (tokenStore().has()) startPolling()
}

// Exposed for tests only — lets a test assert on the sensitivity gate without
// re-deriving the regex, and keeps the import used (autoReplyPolicy already
// imports it for decideReplyAction's own internal use).
export const __testing = { looksSensitive }
