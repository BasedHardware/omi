// Persistent AI-clone state: the Beeper access token (encrypted at rest via
// Electron safeStorage / DPAPI, like integrations/tokenStore.ts), the master
// toggle, per-chat responder modes, pending drafts, and the activity feed.
// Everything lives in one JSON file in userData, written atomically.
//
// Dependencies (file path + encrypt/decrypt) are injected so the store is unit
// testable without electron; service.ts wires the real ones.
import { existsSync, readFileSync, writeFileSync, renameSync, rmSync } from 'fs'
import type { AiCloneChatMode, AiCloneDraft, AiCloneActivityItem } from '../../shared/types'

export type AiCloneStoreDeps = {
  file: string
  encrypt: (plain: string) => string
  decrypt: (stored: string) => string
}

type FileShape = {
  /** Encrypted (deps.encrypt) Beeper access token. */
  beeperToken?: string
  enabled?: boolean
  chatModes?: Record<string, AiCloneChatMode>
  drafts?: AiCloneDraft[]
  activity?: AiCloneActivityItem[]
}

const MAX_ACTIVITY = 100

export class AiCloneStore {
  private data: FileShape = {}

  constructor(private deps: AiCloneStoreDeps) {
    this.load()
  }

  private load(): void {
    if (!existsSync(this.deps.file)) return
    try {
      this.data = JSON.parse(readFileSync(this.deps.file, 'utf8')) as FileShape
    } catch {
      this.data = {} // corrupted file — start fresh rather than crash
    }
  }

  private save(): void {
    const tmp = `${this.deps.file}.tmp`
    writeFileSync(tmp, JSON.stringify(this.data), 'utf8')
    renameSync(tmp, this.deps.file)
  }

  getBeeperToken(): string | null {
    if (!this.data.beeperToken) return null
    try {
      return this.deps.decrypt(this.data.beeperToken)
    } catch {
      return null // encrypted under a different OS user/key — treat as absent
    }
  }

  setBeeperToken(token: string | null): void {
    this.data.beeperToken = token === null ? undefined : this.deps.encrypt(token)
    this.save()
  }

  getEnabled(): boolean {
    return !!this.data.enabled
  }

  setEnabled(enabled: boolean): void {
    this.data.enabled = enabled
    this.save()
  }

  getChatMode(chatId: string): AiCloneChatMode {
    return this.data.chatModes?.[chatId] ?? 'off'
  }

  getChatModes(): Record<string, AiCloneChatMode> {
    return { ...(this.data.chatModes ?? {}) }
  }

  setChatMode(chatId: string, mode: AiCloneChatMode): void {
    const modes = { ...(this.data.chatModes ?? {}) }
    if (mode === 'off') delete modes[chatId]
    else modes[chatId] = mode
    this.data.chatModes = modes
    this.save()
  }

  getDrafts(): AiCloneDraft[] {
    return [...(this.data.drafts ?? [])]
  }

  /** Add a draft, replacing any pending one for the same chat (one per chat). */
  upsertDraft(draft: AiCloneDraft): void {
    this.data.drafts = [...(this.data.drafts ?? []).filter((d) => d.chatId !== draft.chatId), draft]
    this.save()
  }

  removeDraft(draftId: string): AiCloneDraft | null {
    const found = (this.data.drafts ?? []).find((d) => d.id === draftId) ?? null
    if (found) {
      this.data.drafts = (this.data.drafts ?? []).filter((d) => d.id !== draftId)
      this.save()
    }
    return found
  }

  getActivity(): AiCloneActivityItem[] {
    return [...(this.data.activity ?? [])]
  }

  addActivity(item: AiCloneActivityItem): void {
    this.data.activity = [item, ...(this.data.activity ?? [])].slice(0, MAX_ACTIVITY)
    this.save()
  }

  /** Wipe everything (Disconnect). */
  clear(): void {
    this.data = {}
    try {
      rmSync(this.deps.file, { force: true })
    } catch {
      /* best-effort */
    }
  }
}
