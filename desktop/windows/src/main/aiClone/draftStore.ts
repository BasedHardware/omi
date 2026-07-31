// Track 2 (AI clone) — persisted queue of drafted replies waiting for the
// user to approve, edit, or dismiss (Settings → AI Clone's review list). Not
// a credential store: plain JSON, same shape as chatSettingsStore.ts.

import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'
import { randomUUID } from 'crypto'

export interface PendingDraft {
  id: string
  chatID: string
  chatDisplayName: string
  /** The message this is a reply to, for context in the review UI. */
  incomingMessageText: string
  draftText: string
  createdAt: number
}

type StoredFile = PendingDraft[]

export class DraftStore {
  private readonly filePath: string

  constructor(filePath?: string) {
    this.filePath = filePath ?? join(app.getPath('userData'), 'ai-clone-drafts.json')
  }

  private readFile(): StoredFile {
    if (!existsSync(this.filePath)) return []
    try {
      const raw = JSON.parse(readFileSync(this.filePath, 'utf8')) as StoredFile
      return Array.isArray(raw) ? raw : []
    } catch {
      return []
    }
  }

  private writeFile(data: StoredFile): void {
    writeFileSync(this.filePath, JSON.stringify(data), 'utf8')
  }

  list(): PendingDraft[] {
    return this.readFile()
  }

  add(draft: Omit<PendingDraft, 'id' | 'createdAt'>): PendingDraft {
    const record: PendingDraft = { ...draft, id: randomUUID(), createdAt: Date.now() }
    const all = this.readFile()
    all.push(record)
    this.writeFile(all)
    return record
  }

  /** Remove a draft (after it's sent, edited-and-sent, or dismissed). */
  remove(id: string): void {
    this.writeFile(this.readFile().filter((d) => d.id !== id))
  }

  get(id: string): PendingDraft | null {
    return this.readFile().find((d) => d.id === id) ?? null
  }
}
