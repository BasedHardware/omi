// Track 2 (AI clone) — persisted per-chat settings: which chats the user has
// opted in for drafting/auto-send, and the read cursor (chatMonitor.ts's
// latestTimestamp) so a restart doesn't re-poll a chat's whole history.
// Plain JSON (not a credential store — no chat ids here are secrets), same
// synchronous-file-I/O shape as the other stores in this codebase.

import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'
import type { ChatReplyMode } from './autoReplyPolicy'

export interface ChatSetting {
  chatID: string
  displayName: string
  mode: ChatReplyMode
  /** chatMonitor.ts's cursor — undefined until the first poll has run. */
  lastSeenTimestamp?: number
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
      return raw && typeof raw === 'object' ? raw : {}
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
  upsert(setting: Omit<ChatSetting, 'lastSeenTimestamp'>): void {
    const all = this.readFile()
    const existing = all[setting.chatID]
    all[setting.chatID] = { ...setting, lastSeenTimestamp: existing?.lastSeenTimestamp }
    this.writeFile(all)
  }

  /** Advance the read cursor after a poll (chatMonitor.ts's result). */
  setCursor(chatID: string, lastSeenTimestamp: number): void {
    const all = this.readFile()
    const existing = all[chatID]
    if (!existing) return
    all[chatID] = { ...existing, lastSeenTimestamp }
    this.writeFile(all)
  }

  remove(chatID: string): void {
    const all = this.readFile()
    delete all[chatID]
    this.writeFile(all)
  }
}
