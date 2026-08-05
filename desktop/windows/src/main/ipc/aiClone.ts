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
import { decideReplyAction, isValidChatMode, looksSensitive } from '../aiClone/autoReplyPolicy'
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

// Guards against overlapping pollAiCloneChats runs — a slow chat fetch, a
// manual trigger racing the interval, or a tick firing while the previous one
// is still awaiting a network call could otherwise run two passes at once and
// double-broadcast the same message.
let pollInProgress = false

// Message ids currently broadcast to the renderer and awaiting an
// aiCloneSubmitDraft callback, keyed to when they were broadcast. This stops
// the same still-in-flight message from being re-broadcast on the very next
// poll tick — normal draft round-trip latency (one LLM call) is well under
// IN_FLIGHT_STALE_MS. An entry older than that is treated as abandoned (the
// renderer crashed, or silently swallowed an error without calling back) and
// becomes eligible for a retry broadcast rather than being lost forever.
const inFlightMessages = new Map<string, number>()
const IN_FLIGHT_STALE_MS = POLL_INTERVAL_MS * 3

function isInFlight(messageId: string): boolean {
  const startedAt = inFlightMessages.get(messageId)
  if (startedAt === undefined) return false
  if (Date.now() - startedAt > IN_FLIGHT_STALE_MS) {
    inFlightMessages.delete(messageId)
    return false
  }
  return true
}

/** Advance a chat's read cursor only forward, and only when called — this is
 *  invoked from the submitDraft handler once a message's processing outcome
 *  is known (sent, queued, or explicitly skipped), never optimistically at
 *  poll time. That way a message that's still being drafted when the process
 *  restarts, or whose draft call fails, is picked up again on the next poll
 *  instead of being silently marked "seen" and lost. */
function advanceCursorIfNewer(chatID: string, messageTimestamp: number): void {
  const setting = chatSettings().get(chatID)
  if (!setting) return
  if (setting.lastSeenTimestamp !== undefined && messageTimestamp <= setting.lastSeenTimestamp) {
    return
  }
  chatSettings().setCursor(chatID, messageTimestamp)
}

/** One poll pass over every opted-in chat. Exported for the interval below
 *  and for a manual "check now" if a future UI wants one; errors on a single
 *  chat never abort the rest of the cycle. */
export async function pollAiCloneChats(client: BeeperClient = clientOrNull()!): Promise<void> {
  if (pollInProgress) return
  pollInProgress = true
  try {
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

        // Nothing async pending for this chat this tick (either no new
        // messages, or this is the first-ever poll establishing a baseline
        // cursor) — safe to advance immediately, matching
        // chatMonitor.ts's documented first-poll behavior.
        if (newMessages.length === 0) {
          if (latestTimestamp !== undefined) {
            chatSettings().setCursor(setting.chatID, latestTimestamp)
          }
          continue
        }

        for (const incoming of newMessages) {
          if (isInFlight(incoming.id)) continue

          const index = ascending.findIndex((m) => m.id === incoming.id)
          const historyMessages = (index >= 0 ? ascending.slice(0, index) : []).slice(
            -HISTORY_WINDOW
          )
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
          // messages array. Label each turn explicitly rather than just
          // concatenating them, so the instruction/data boundary
          // personaDraftPrompt.ts establishes survives being flattened —
          // the untrusted <untrusted_chat_content> fencing lives inside the
          // user turn either way, but this keeps the system turn visually
          // and textually distinct from it too.
          const promptText = prompt
            .map((m) => `[${m.role.toUpperCase()} INSTRUCTIONS]\n${m.content}`)
            .join('\n\n')

          inFlightMessages.set(incoming.id, Date.now())

          const event: AiCloneIncomingMessageEvent = {
            chatID: setting.chatID,
            chatDisplayName: setting.displayName,
            mode: setting.mode,
            incomingMessageText: incoming.text ?? '',
            messageID: incoming.id,
            messageTimestamp: incoming.timestamp,
            promptText
          }
          broadcast('aiClone:incomingMessage', event)
        }
      } catch (error) {
        console.log(`[aiClone] poll failed for chat ${setting.chatID}: ${messageText(error)}`)
      }
    }
  } finally {
    pollInProgress = false
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

/** Sign-out / account-switch teardown. Called from main/ipc/db.ts's
 *  wipeUserData alongside the other user-scoped, file-backed stores
 *  (ByokKeyStore, McpKeyStore) — see that file's own comment for why those
 *  live outside the SQLite wipe. AI Clone's Beeper token, per-chat settings,
 *  and queued drafts are exactly the same shape of problem: none of them are
 *  tied to the signed-in Omi account today, so without this, a different
 *  account signing in on this machine would inherit the previous user's
 *  Beeper connection, which chats were opted into auto-reply, and any
 *  drafted replies still sitting in the review queue (which can contain the
 *  previous user's private message content). Best-effort per store, mirroring
 *  wipeUserData's own try/catch-per-store pattern, so one store's failure
 *  doesn't leave the others uncleared. */
export function clearAiCloneUserData(): void {
  stopAiClonePolling()
  cachedClient = null
  pollInProgress = false
  inFlightMessages.clear()
  try {
    tokenStore().clearAll()
  } catch {
    /* best-effort */
  }
  try {
    chatSettings().clearAll()
  } catch {
    /* best-effort */
  }
  try {
    drafts().clearAll()
  } catch {
    /* best-effort */
  }
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
      // Fail closed: a stale/mismatched renderer build or a malformed IPC
      // call could hand this an arbitrary string despite the TS signature.
      // Never persist something decideReplyAction hasn't been told how to
      // interpret.
      const safeMode = isValidChatMode(mode) ? mode : 'off'
      chatSettings().upsert({ chatID, displayName, mode: safeMode })
    }
  )

  ipcMain.handle('aiClone:listDrafts', (): AiClonePendingDraft[] => drafts().list())

  // In-memory guard for approveDraft: closes the gap between take()'s
  // synchronous find-and-remove and the network send that follows it. take()
  // alone already stops two overlapping calls from both finding the draft,
  // but this also gives a fast, explicit "already handled" no-op for a
  // double-click that lands while the first click's send is still in flight.
  const resolvingDraftIds = new Set<string>()

  ipcMain.handle(
    'aiClone:approveDraft',
    async (_e, id: string, editedText?: string): Promise<void> => {
      if (resolvingDraftIds.has(id)) return
      resolvingDraftIds.add(id)
      try {
        // take() removes the draft from the store BEFORE we attempt to send
        // it — not after — so a draft can never be sent twice even if the
        // send itself is slow or a second request slips in mid-flight.
        const draft = drafts().take(id)
        if (!draft) return
        const textToSend = editedText?.trim() || draft.draftText
        try {
          await resolveDraftSend(draft.chatID, textToSend)
        } catch (error) {
          // The send failed after we'd already removed it from the queue —
          // put it back so a transient network error doesn't silently
          // discard the user's reviewed reply. This can't reintroduce the
          // double-send this whole guard exists to prevent: nothing else
          // could have taken() this id in the meantime, since it was gone
          // from the store for the entire duration of the failed attempt.
          drafts().add({
            chatID: draft.chatID,
            chatDisplayName: draft.chatDisplayName,
            incomingMessageText: draft.incomingMessageText,
            draftText: textToSend
          })
          throw error
        }
      } finally {
        resolvingDraftIds.delete(id)
      }
    }
  )

  ipcMain.handle('aiClone:dismissDraft', (_e, id: string): void => {
    drafts().remove(id)
  })

  // Guards against the same Beeper message being resolved twice — e.g. a
  // stale/duplicate broadcast from the in-flight staleness fallback landing
  // just as the original round-trip finally comes back.
  const resolvingMessageIds = new Set<string>()

  ipcMain.handle(
    'aiClone:submitDraft',
    async (_e, args: AiCloneSubmitDraftArgs): Promise<AiCloneSubmitDraftResult> => {
      if (resolvingMessageIds.has(args.messageID)) {
        return { action: 'skipped' }
      }
      resolvingMessageIds.add(args.messageID)
      try {
        const setting = chatSettings().get(args.chatID)
        const mode = setting?.mode ?? 'off'
        const decision = decideReplyAction({
          mode,
          draftText: args.draftText,
          needsInput: draftNeedsInput(args.draftText)
        })

        let result: AiCloneSubmitDraftResult
        if (decision === 'skip') {
          result = { action: 'skipped' }
        } else if (decision === 'send') {
          // If this throws, we deliberately fall out of the try block below
          // without advancing the cursor or releasing the in-flight marker —
          // the message stays eligible for a retry broadcast rather than
          // being marked processed when it wasn't.
          await resolveDraftSend(args.chatID, args.draftText)
          result = { action: 'sent' }
        } else {
          const draft = drafts().add({
            chatID: args.chatID,
            chatDisplayName: args.chatDisplayName,
            incomingMessageText: args.incomingMessageText,
            draftText: args.draftText
          })
          result = { action: 'queued_for_review', draft }
        }

        // Only reached once the decision was fully carried out — this is
        // the "successful processing" the cursor and in-flight tracking are
        // gated on.
        advanceCursorIfNewer(args.chatID, args.messageTimestamp)
        inFlightMessages.delete(args.messageID)
        return result
      } finally {
        resolvingMessageIds.delete(args.messageID)
      }
    }
  )

  if (tokenStore().has()) startPolling()
}

// Exposed for tests only — lets a test assert on the sensitivity gate without
// re-deriving the regex, and keeps the import used (autoReplyPolicy already
// imports it for decideReplyAction's own internal use).
export const __testing = { looksSensitive }
