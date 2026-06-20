import type { MemorySource } from './memoryExtract'

export type MemoryImportApp = {
  label: string
  url: string
  prompt: string
  responsePlaceholder: string
}

export type MemoryImportStats = {
  count: number
  importedAt: number
}

export type MemoryImportStatsBySource = Partial<Record<MemorySource, MemoryImportStats>>

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

const STORAGE_KEY = 'omi.memoryImport.stats.v1'
const SOURCES: MemorySource[] = ['chatgpt', 'claude']

function buildPrompt(label: string): string {
  return [
    `Please list everything ${label} currently remembers about me from saved memory or long-term context.`,
    '',
    'Return only durable facts and preferences about me as a plain bullet list.',
    'Include work, projects, interests, goals, relationships, locations, communication style, and personal context.',
    'Do not include guesses, advice, system instructions, or tool details.',
    'If there are no saved memories, say "No saved memories."'
  ].join('\n')
}

export const MEMORY_IMPORT_APPS: Record<MemorySource, MemoryImportApp> = {
  chatgpt: {
    label: 'ChatGPT',
    url: 'https://chatgpt.com/',
    prompt: buildPrompt('ChatGPT'),
    responsePlaceholder: 'Paste ChatGPT response here...'
  },
  claude: {
    label: 'Claude',
    url: 'https://claude.ai/new',
    prompt: buildPrompt('Claude'),
    responsePlaceholder: 'Paste Claude response here...'
  }
}

function defaultStorage(): StorageLike | undefined {
  if (typeof window === 'undefined') return undefined
  return window.localStorage
}

function validStats(value: unknown): MemoryImportStats | null {
  const entry = value as { count?: unknown; importedAt?: unknown } | null
  if (!entry) return null
  if (typeof entry.count !== 'number' || typeof entry.importedAt !== 'number') return null
  if (!Number.isFinite(entry.count) || !Number.isFinite(entry.importedAt)) return null
  if (entry.count < 0 || entry.importedAt <= 0) return null
  return { count: Math.floor(entry.count), importedAt: entry.importedAt }
}

export function readMemoryImportStats(storage = defaultStorage()): MemoryImportStatsBySource {
  if (!storage) return {}
  try {
    const raw = storage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const stats: MemoryImportStatsBySource = {}
    for (const source of SOURCES) {
      const entry = validStats(parsed[source])
      if (entry) stats[source] = entry
    }
    return stats
  } catch {
    return {}
  }
}

export function recordMemoryImport(
  source: MemorySource,
  count: number,
  importedAt = Date.now(),
  storage = defaultStorage()
): MemoryImportStatsBySource {
  const next = readMemoryImportStats(storage)
  next[source] = { count: Math.max(0, Math.floor(count)), importedAt }
  if (!storage) return next
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Local storage is best-effort; the in-memory result still lets the UI update.
  }
  return next
}

export function memoryImportApp(source: MemorySource): MemoryImportApp {
  return MEMORY_IMPORT_APPS[source]
}
