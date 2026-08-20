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
import {
  BeeperClient,
  BEEPER_BASE_URL,
  beeperTimestampMs,
  discoverBeeperBaseUrl,
  oldestFirst,
  type BeeperChat,
  type BeeperMessage
} from './beeperClient'
import { decide, AUTO_SEND_HOURLY_CAP } from './responder'
import { ChatTaskQueue } from './chatTaskQueue'
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
  /** Per-chat serializer: one reply at a time per chat, later arrivals parked. */
  private queue = new ChatTaskQueue()
  /** id → chat metadata cache for titles/types in decisions and drafts. */
  private chatCache = new Map<string, BeeperChat>()
  /** Port Beeper Desktop was found on (23373 or 23374 depending on the build). */
  private beeperBaseUrl = BEEPER_BASE_URL
  /** Bumped whenever listening stops. Reply work captures the value it started
   *  under, so a generation that was already in flight (or parked behind one)
   *  when the user disabled or disconnected can never land a draft afterwards. */
  private generation = 0

  constructor(
    private broadcast: (e: AiCloneEvent) => void,
    private replyGenerator = generateReply
  ) {
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
    if (token) {
      this.client = new BeeperClient(token, this.beeperBaseUrl)
      // Resume listening on app start if the user left the clone enabled —
      // after locating the port this Beeper build actually binds.
      void discoverBeeperBaseUrl().then((base) => {
        this.beeperBaseUrl = base
        this.client = new BeeperClient(token, base)
        if (this.store.getEnabled()) this.startListening()
      })
    }
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
    this.beeperBaseUrl = await discoverBeeperBaseUrl()
    const probe = await new BeeperClient(beeperToken, this.beeperBaseUrl).validateToken()
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
    this.client = new BeeperClient(beeperToken, this.beeperBaseUrl)
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
    // An empty token is the renderer saying "this session is gone" (sign-out or
    // an account switch): drop it rather than storing a falsy credential.
    this.firebaseToken = auth.token || null
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
          this.handleIncoming(e.chatID, entry)
        }
      }
    })
  }

  private stopListening(): void {
    this.subscription?.close()
    this.subscription = null
    this.beeperReachable = false
    // Retire every reply that is already generating or parked behind one: the
    // user turned the clone off, so none of them may still produce a draft.
    this.generation += 1
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

  private handleIncoming(chatID: string, message: BeeperMessage): void {
    const messageId = message.id
    if (!messageId || this.processed.has(messageId)) return
    // Serialize per chat through the queue — a message arriving while this
    // chat's reply is still generating is parked and handled right after
    // (previously an in-flight guard silently dropped it). The decision runs
    // inside the task, at execution time, so a parked message is judged
    // against current state (mode changes, hourly cap, …).
    const generation = this.generation
    this.queue.submit(chatID, async () => {
      if (!this.client || this.processed.has(messageId)) return
      // Parked work can execute long after it was queued; if listening stopped
      // in between, this message belongs to a session the user ended.
      if (generation !== this.generation) return
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
      // Only accepted messages are marked processed — ignores stay cheap to
      // re-decide, and a parked-then-superseded message was never marked.
      if (await this.respond(chat, message, generation)) this.markProcessed(messageId)
    })
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
    generation: number
  ): Promise<boolean> {
    const chatTitle = chat.title ?? chat.id
    if (!this.firebaseToken) {
      this.recordError(chatTitle, 'No Omi session token — open the AI Clone page to refresh')
      this.broadcast({ kind: 'token-expired' })
      return false
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
    let reply = await this.replyGenerator({ ...engineArgs, firebaseToken: this.firebaseToken, ctx })
    if (!reply.ok && reply.error === 'unauthorized') {
      // The token can sit in main for up to an hour, so expiry mid-session is
      // routine — ask the renderer for a fresh one and retry this message once
      // instead of dropping it.
      this.firebaseToken = null
      this.broadcast({ kind: 'token-expired' })
      const fresh = await this.waitForToken(5_000)
      if (fresh) {
        reply = await this.replyGenerator({ ...engineArgs, firebaseToken: fresh, ctx })
      }
    }
    if (!reply.ok) {
      this.recordError(
        chatTitle,
        reply.error === 'unauthorized'
          ? 'Omi session expired — reply skipped'
          : (reply.detail ?? `Reply generation failed (${reply.error})`)
      )
      return false
    }

    // Generation may have moved on while the model was answering (disable or
    // disconnect, which also wipes the store) — never resurrect a draft into
    // state the user just cleared.
    if (generation !== this.generation) return false

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
    return true
  }

  private async recentTranscript(
    chatID: string,
    excludeMessageId: string
  ): Promise<ReplyTranscriptLine[]> {
    const r = await this.client!.listMessages(chatID)
    if (!r.ok) return []
    return oldestFirst(r.value)
      .filter((m) => m.id !== excludeMessageId && m.text?.trim() && !m.isDeleted)
      .slice(-TRANSCRIPT_LINES)
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
