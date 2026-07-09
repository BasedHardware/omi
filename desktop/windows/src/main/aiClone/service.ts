// AI-clone orchestrator: owns the Beeper connection, runs the listen loop in
// the main process (so it survives renderer navigation), and turns incoming
// messages into drafts or auto-sent replies. The renderer configures it over
// IPC and supplies Firebase ID tokens for /v2/messages (main never refreshes
// them itself — same division as memoriesBulkDelete).
import { app, safeStorage, Notification } from 'electron'
import { join } from 'path'
import { randomUUID } from 'crypto'
import type {
  AiCloneAuth,
  AiCloneChat,
  AiCloneChatMode,
  AiCloneDraft,
  AiCloneEvent,
  AiCloneState
} from '../../shared/types'
import { AiCloneStore } from './store'
import { BeeperClient, beeperTimestampMs, type BeeperChat, type BeeperMessage } from './beeperClient'
import { decide, AUTO_SEND_HOURLY_CAP } from './responder'
import { generateReply, type ReplyTranscriptLine } from './replyEngine'

const DEFAULT_API_BASE = 'https://api.omi.me'
const TRANSCRIPT_LINES = 10

export class AiCloneService {
  private store: AiCloneStore
  private client: BeeperClient | null = null
  private subscription: { close: () => void } | null = null
  private beeperReachable = false
  private sessionStartedAt = 0
  private apiBase = DEFAULT_API_BASE
  private desktopApiBase: string | undefined
  private firebaseToken: string | null = null
  private displayName = ''
  private lastError: string | undefined
  /** Rolling auto-send timestamps for the hourly cap. */
  private autoSends: number[] = []
  /** message ids already handled — WS re-delivers upserts for edits/reactions. */
  private processed = new Set<string>()
  /** chats with a reply generation in flight (one at a time per chat). */
  private inFlight = new Set<string>()
  /** id → chat metadata cache for titles/types in decisions and drafts. */
  private chatCache = new Map<string, BeeperChat>()

  constructor(private broadcast: (e: AiCloneEvent) => void) {
    this.store = new AiCloneStore({
      file: join(app.getPath('userData'), 'ai-clone.json'),
      encrypt: (s) => {
        if (!safeStorage.isEncryptionAvailable()) {
          throw new Error('Secure storage is unavailable on this system')
        }
        return safeStorage.encryptString(s).toString('base64')
      },
      decrypt: (s) => safeStorage.decryptString(Buffer.from(s, 'base64'))
    })
    // A client exists whenever a token does (listChats/approveDraft work while
    // the responder is off); the WS subscription only runs while enabled.
    const token = this.store.getBeeperToken()
    if (token) this.client = new BeeperClient(token)
    // Resume listening on app start if the user left the clone enabled.
    if (this.store.getEnabled() && this.client) this.startListening()
  }

  // --- state ---

  getState(): AiCloneState {
    return {
      beeperConnected: !!this.store.getBeeperToken(),
      beeperReachable: this.beeperReachable,
      enabled: this.store.getEnabled(),
      authTokenPresent: !!this.firebaseToken,
      pendingDrafts: this.store.getDrafts(),
      activity: this.store.getActivity(),
      autoSentThisHour: this.autoSentThisHour(),
      error: this.lastError
    }
  }

  private emitState(): void {
    this.broadcast({ kind: 'state', state: this.getState() })
  }

  private autoSentThisHour(): number {
    const cutoff = Date.now() - 3_600_000
    this.autoSends = this.autoSends.filter((t) => t > cutoff)
    return this.autoSends.length
  }

  // --- connection lifecycle ---

  async connect(beeperToken: string): Promise<AiCloneState> {
    const probe = await new BeeperClient(beeperToken).validateToken()
    if (!probe.ok) {
      this.lastError =
        probe.error === 'unreachable'
          ? 'Beeper Desktop is not running (or its API is disabled)'
          : probe.error === 'unauthorized'
            ? 'Beeper rejected that token'
            : (probe.detail ?? 'Beeper request failed')
      this.emitState()
      return this.getState()
    }
    this.store.setBeeperToken(beeperToken)
    this.client = new BeeperClient(beeperToken)
    this.beeperReachable = true
    this.lastError = undefined
    if (this.store.getEnabled()) this.startListening()
    this.emitState()
    return this.getState()
  }

  disconnect(): AiCloneState {
    this.stopListening()
    this.client = null
    this.chatCache.clear()
    this.store.clear()
    this.beeperReachable = false
    this.lastError = undefined
    this.emitState()
    return this.getState()
  }

  setEnabled(enabled: boolean, auth?: AiCloneAuth): AiCloneState {
    if (auth) this.applyAuth(auth)
    this.store.setEnabled(enabled)
    if (enabled && this.store.getBeeperToken()) this.startListening()
    if (!enabled) this.stopListening()
    this.emitState()
    return this.getState()
  }

  provideAuthToken(auth: AiCloneAuth): void {
    this.applyAuth(auth)
    this.emitState()
  }

  private applyAuth(auth: AiCloneAuth): void {
    this.firebaseToken = auth.token
    if (auth.apiBase) this.apiBase = auth.apiBase
    if (auth.desktopApiBase) this.desktopApiBase = auth.desktopApiBase
    if (auth.displayName !== undefined) this.displayName = auth.displayName
  }

  private startListening(): void {
    if (this.subscription || !this.client) return
    this.sessionStartedAt = Date.now()
    this.subscription = this.client.subscribe({
      onUp: () => {
        this.beeperReachable = true
        this.lastError = undefined
        this.emitState()
        void this.refreshChatCache()
      },
      onDown: () => {
        if (this.beeperReachable) {
          this.beeperReachable = false
          this.emitState()
        }
      },
      onEvent: (e) => {
        if (e.type !== 'message.upserted' || !e.chatID) return
        for (const entry of e.entries ?? []) {
          void this.handleIncoming(e.chatID, entry)
        }
      }
    })
  }

  private stopListening(): void {
    this.subscription?.close()
    this.subscription = null
    this.beeperReachable = false
  }

  // --- chats ---

  private async refreshChatCache(): Promise<void> {
    if (!this.client) return
    const r = await this.client.listChats()
    if (r.ok) for (const c of r.value) this.chatCache.set(c.id, c)
  }

  async listChats(): Promise<AiCloneChat[]> {
    await this.refreshChatCache()
    const chats = [...this.chatCache.values()].map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      network: c.network ?? 'unknown',
      type: c.type === 'group' ? ('group' as const) : ('single' as const),
      mode: this.store.getChatMode(c.id),
      lastActivityAt: beeperTimestampMs(c.lastActivity)
    }))
    return chats.sort((a, b) => (b.lastActivityAt ?? 0) - (a.lastActivityAt ?? 0))
  }

  setChatMode(chatId: string, mode: AiCloneChatMode): void {
    this.store.setChatMode(chatId, mode)
    this.emitState()
  }

  // --- the responder loop ---

  private async handleIncoming(chatID: string, message: BeeperMessage): Promise<void> {
    if (!this.client || !message.id || this.processed.has(message.id)) return
    let chat = this.chatCache.get(chatID)
    if (!chat) {
      await this.refreshChatCache()
      chat = this.chatCache.get(chatID) ?? { id: chatID }
    }
    const decision = decide({
      message,
      chatType: chat.type === 'group' ? 'group' : 'single',
      chatMode: this.store.getChatMode(chatID),
      sessionStartedAt: this.sessionStartedAt,
      autoSentThisHour: this.autoSentThisHour(),
      autoSendHourlyCap: AUTO_SEND_HOURLY_CAP
    })
    if (decision.action === 'ignore') return
    this.markProcessed(message.id)
    if (this.inFlight.has(chatID)) return
    this.inFlight.add(chatID)
    try {
      await this.respond(chat, message, decision.action)
    } finally {
      this.inFlight.delete(chatID)
    }
  }

  private markProcessed(id: string): void {
    this.processed.add(id)
    if (this.processed.size > 2_000) {
      // Drop the oldest half (Set iterates in insertion order).
      const keep = [...this.processed].slice(-1_000)
      this.processed = new Set(keep)
    }
  }

  private async respond(
    chat: BeeperChat,
    message: BeeperMessage,
    action: 'draft' | 'autoSend'
  ): Promise<void> {
    const chatTitle = chat.title ?? chat.id
    if (!this.firebaseToken) {
      this.recordError(chatTitle, 'No Omi session token — open the AI Clone page to refresh')
      this.broadcast({ kind: 'token-expired' })
      return
    }
    const ctx = {
      userDisplayName: this.displayName,
      senderName: message.senderName ?? chatTitle,
      chatTitle,
      network: chat.network ?? 'chat',
      transcript: await this.recentTranscript(chat.id, message.id),
      incomingText: message.text ?? ''
    }
    const engineArgs = { apiBase: this.apiBase, desktopApiBase: this.desktopApiBase }
    let reply = await generateReply({ ...engineArgs, firebaseToken: this.firebaseToken, ctx })
    if (!reply.ok && reply.error === 'unauthorized') {
      // The token can sit in main for up to an hour, so expiry mid-session is
      // routine — ask the renderer for a fresh one and retry this message once
      // instead of dropping it.
      this.firebaseToken = null
      this.broadcast({ kind: 'token-expired' })
      const fresh = await this.waitForToken(5_000)
      if (fresh) {
        reply = await generateReply({ ...engineArgs, firebaseToken: fresh, ctx })
      }
    }
    if (!reply.ok) {
      this.recordError(
        chatTitle,
        reply.error === 'unauthorized'
          ? 'Omi session expired — reply skipped'
          : (reply.detail ?? `Reply generation failed (${reply.error})`)
      )
      return
    }

    if (action === 'autoSend') {
      const sent = await this.client!.sendMessage(chat.id, reply.text, message.id)
      if (sent.ok) {
        this.autoSends.push(Date.now())
        this.store.addActivity({
          id: randomUUID(),
          at: Date.now(),
          kind: 'auto_sent',
          chatTitle,
          text: reply.text
        })
        this.emitState()
      } else {
        this.recordError(chatTitle, `Send failed (${sent.error})`)
      }
      return
    }

    const draft: AiCloneDraft = {
      id: randomUUID(),
      chatId: chat.id,
      chatTitle,
      network: chat.network ?? 'chat',
      senderName: message.senderName ?? chatTitle,
      incomingText: message.text ?? '',
      incomingMessageId: message.id,
      replyText: reply.text,
      createdAt: Date.now()
    }
    this.store.upsertDraft(draft)
    this.emitState()
    this.notifyDraft(draft)
  }

  private async recentTranscript(
    chatID: string,
    excludeMessageId: string
  ): Promise<ReplyTranscriptLine[]> {
    const r = await this.client!.listMessages(chatID)
    if (!r.ok) return []
    return r.value
      .filter((m) => m.id !== excludeMessageId && m.text?.trim() && !m.isDeleted)
      .slice(0, TRANSCRIPT_LINES)
      .reverse()
      .map((m) => ({
        sender: m.senderName ?? 'them',
        text: m.text!,
        fromMe: !!m.isSender
      }))
  }

  /** Poll for a renderer-supplied token after a token-expired broadcast. */
  private async waitForToken(timeoutMs: number): Promise<string | null> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (this.firebaseToken) return this.firebaseToken
      await new Promise((r) => setTimeout(r, 250))
    }
    return this.firebaseToken
  }

  private recordError(chatTitle: string, text: string): void {
    this.lastError = text
    this.store.addActivity({ id: randomUUID(), at: Date.now(), kind: 'error', chatTitle, text })
    this.emitState()
  }

  private notifyDraft(draft: AiCloneDraft): void {
    if (!Notification.isSupported()) return
    const n = new Notification({
      title: `AI Clone drafted a reply to ${draft.senderName}`,
      body: draft.replyText,
      silent: true
    })
    n.show()
  }

  // --- drafts ---

  async approveDraft(draftId: string, editedText?: string): Promise<AiCloneState> {
    const draft = this.store.removeDraft(draftId)
    if (!draft || !this.client) {
      this.emitState()
      return this.getState()
    }
    const text = editedText?.trim() || draft.replyText
    const sent = await this.client.sendMessage(draft.chatId, text, draft.incomingMessageId)
    if (sent.ok) {
      this.store.addActivity({
        id: randomUUID(),
        at: Date.now(),
        kind: 'draft_sent',
        chatTitle: draft.chatTitle,
        text
      })
      this.lastError = undefined
    } else {
      // Sending failed (Beeper closed?) — put the draft back so nothing is lost.
      this.store.upsertDraft({ ...draft, replyText: text })
      this.lastError = `Send failed (${sent.error})`
    }
    this.emitState()
    return this.getState()
  }

  discardDraft(draftId: string): AiCloneState {
    const draft = this.store.removeDraft(draftId)
    if (draft) {
      this.store.addActivity({
        id: randomUUID(),
        at: Date.now(),
        kind: 'draft_dismissed',
        chatTitle: draft.chatTitle,
        text: draft.replyText
      })
    }
    this.emitState()
    return this.getState()
  }
}
