// Persisted handled-message ids + pending drafts. Not secret (no token).
import { app } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import type { BeeperDraft } from '../../shared/types'

type BeeperState = {
  handled: Record<string, string>
  drafts: BeeperDraft[]
}

function file(): string {
  return join(app.getPath('userData'), 'beeper-state.json')
}

function empty(): BeeperState {
  return { handled: {}, drafts: [] }
}

export function loadBeeperState(): BeeperState {
  const f = file()
  if (!existsSync(f)) return empty()
  try {
    const raw = JSON.parse(readFileSync(f, 'utf8')) as Partial<BeeperState>
    return {
      handled: raw.handled && typeof raw.handled === 'object' ? raw.handled : {},
      drafts: Array.isArray(raw.drafts) ? raw.drafts : []
    }
  } catch {
    return empty()
  }
}

function save(state: BeeperState): void {
  writeFileSync(file(), JSON.stringify(state), 'utf8')
}

export function getHandledMessageId(chatId: string): string | undefined {
  return loadBeeperState().handled[chatId]
}

export function markHandled(chatId: string, messageId: string): void {
  const state = loadBeeperState()
  state.handled[chatId] = messageId
  save(state)
}

export function listDrafts(): BeeperDraft[] {
  return loadBeeperState().drafts
}

export function addDraft(draft: BeeperDraft): void {
  const state = loadBeeperState()
  if (state.drafts.some((d) => d.inboundMessageId === draft.inboundMessageId)) return
  state.drafts.push(draft)
  state.handled[draft.chatId] = draft.inboundMessageId
  save(state)
}

export function removeDraft(id: string): BeeperDraft | null {
  const state = loadBeeperState()
  const found = state.drafts.find((d) => d.id === id) ?? null
  state.drafts = state.drafts.filter((d) => d.id !== id)
  save(state)
  return found
}

export function clearBeeperState(): void {
  save(empty())
}
