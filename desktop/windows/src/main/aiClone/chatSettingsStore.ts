// Track 2 (AI clone) — persisted per-chat settings: which chats the user has
// opted in for drafting/auto-send, and the read cursor (chatMonitor.ts's
// latestTimestamp) so a restart doesn't re-poll a chat's whole history.
// Plain JSON (not a credential store — no chat ids here are secrets), same
// synchronous-file-I/O shape as the other stores in this codebase.

import { existsSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'
import { isValidChatMode, type ChatReplyMode } from './autoReplyPolicy'

export interface ChatSetting {
  chatID: string
  displayName: string
  mode: ChatReplyMode
  /** chatMonitor.ts's cursor — undefined until the first poll has run. */
  lastSeenTimestamp?: number
  /** Message ids at exactly lastSeenTimestamp — see chatMonitor.ts's
   *  NewInboundResult for why a single timestamp isn't enough to avoid
   *  either re-drafting or silently dropping a message that shares the
   *  cursor's exact millisecond. */
  lastSeenMessageIds?: string[]
}

type StoredFile = Record<string, ChatSetting>

export class ChatSettingsStore {
  private readonly filePath: string

  constructor(filePath?: string) {
    this.filePath = filePath ?? join(app.getPath('userData'), 'ai-clone-chat-settings.json')
  }

  private readFile(): StoredFile {
    if (!existsSync(this.filePath)) return {}
    try {
      const raw = JSON.parse(readFileSync(this.filePath, 'utf8')) as StoredFile
      if (!raw || typeof raw !== 'object') return {}
      // Fail closed: a hand-edited or corrupted file could contain anything
      // in `mode`. If it's not one of the three real values, coerce to 'off'
      // rather than letting an unrecognized string reach decideReplyAction —
      // that function has its own backstop too, but the fix belongs here,
      // at the point untrusted data enters the system.
      const sanitized: StoredFile = {}
      for (const [chatID, setting] of Object.entries(raw)) {
        if (!setting || typeof setting !== 'object' || typeof setting.chatID !== 'string') continue
        sanitized[chatID] = {
          ...setting,
          mode: isValidChatMode(setting.mode) ? setting.mode : 'off'
        }
      }
      return sanitized
    } catch {
      return {}
    }
  }

  private writeFile(data: StoredFile): void {
    writeFileSync(this.filePath, JSON.stringify(data), 'utf8')
  }

  list(): ChatSetting[] {
    return Object.values(this.readFile())
  }

  get(chatID: string): ChatSetting | null {
    return this.readFile()[chatID] ?? null
  }

  /** Create or update a chat's mode/display name. Preserves the existing
   *  cursor unless the caller explicitly clears it (e.g. re-opting back in
   *  after 'off' should NOT retroactively draft the gap — same first-poll
   *  behavior chatMonitor already gives an untouched chat). */
  upsert(setting: Omit<ChatSetting, 'lastSeenTimestamp' | 'lastSeenMessageIds'>): void {
    const all = this.readFile()
    const existing = all[setting.chatID]
    all[setting.chatID] = {
      ...setting,
      lastSeenTimestamp: existing?.lastSeenTimestamp,
      lastSeenMessageIds: existing?.lastSeenMessageIds
    }
    this.writeFile(all)
  }

  /** Advance the read cursor after a poll (chatMonitor.ts's result). */
  setCursor(chatID: string, lastSeenTimestamp: number, lastSeenMessageIds: string[] = []): void {
    const all = this.readFile()
    const existing = all[chatID]
    if (!existing) return
    all[chatID] = { ...existing, lastSeenTimestamp, lastSeenMessageIds }
    this.writeFile(all)
  }

  remove(chatID: string): void {
    const all = this.readFile()
    delete all[chatID]
    this.writeFile(all)
  }

  /** Drop every chat setting (opted-in chats, modes, cursors). Called on
   *  sign-out / account switch — see main/ipc/db.ts's wipeUserData — so a
   *  different Omi account on this machine never inherits which of the
   *  previous user's Beeper chats were opted into drafting or auto-send. */
  clearAll(): void {
    if (existsSync(this.filePath)) rmSync(this.filePath, { force: true })
  }
}
