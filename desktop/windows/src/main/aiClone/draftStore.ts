// Track 2 (AI clone) — persisted queue of drafted replies waiting for the
// user to approve, edit, or dismiss (Settings → AI Clone's review list). Not
// a credential store: plain JSON, same shape as chatSettingsStore.ts.

import { existsSync, readFileSync, rmSync, writeFileSync } from 'fs'
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
  /** ipc/aiClone.ts's session generation at the time this draft was queued —
   *  bumped on connect/disconnect/sign-out. A draft whose generation no
   *  longer matches the current one belongs to a Beeper connection (or
   *  account) that isn't live anymore; its chatID is meaningless under
   *  whatever's connected now and it must not be sent. */
  sessionGeneration: number
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

  /** Atomically find-and-remove a draft in a single synchronous read/write
   *  pass — no `await` between the read and the write, so two overlapping
   *  approve calls for the same id (a double-click, or a race between the
   *  UI and a background auto-send) cannot both see the draft still present.
   *  The second caller always gets `null` here and must no-op. Callers
   *  should take() BEFORE sending, not after, so a draft can never be sent
   *  twice even if the send itself is slow. */
  take(id: string): PendingDraft | null {
    const all = this.readFile()
    const index = all.findIndex((d) => d.id === id)
    if (index === -1) return null
    const [draft] = all.splice(index, 1)
    this.writeFile(all)
    return draft
  }

  /** Drop every queued draft. Called on sign-out / account switch — see
   *  main/ipc/db.ts's wipeUserData — so a different Omi account on this
   *  machine never inherits drafted replies containing the previous user's
   *  private message content. */
  clearAll(): void {
    if (existsSync(this.filePath)) rmSync(this.filePath, { force: true })
  }
}
