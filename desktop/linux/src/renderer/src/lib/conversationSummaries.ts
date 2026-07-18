// src/renderer/src/lib/conversationSummaries.ts
// Persistent store for auto-generated conversation summaries (localStorage)
import type { SummaryResult } from './summaryClient'

const STORAGE_KEY = 'conversation-summaries-v1'

type SummaryStore = Record<string, SummaryResult>

function load(): SummaryStore {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {}
}

function save(store: SummaryStore): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
}

export const conversationSummaries = {
  get(conversationId: string): SummaryResult | null {
    return load()[conversationId] ?? null
  },

  set(conversationId: string, result: SummaryResult): void {
    const store = load()
    store[conversationId] = result
    save(store)
  },

  has(conversationId: string): boolean {
    return conversationId in load()
  },

  getAll(): Array<{ conversationId: string } & SummaryResult> {
    const store = load()
    return Object.entries(store).map(([id, result]) => ({
      conversationId: id,
      ...result
    }))
  }
}
