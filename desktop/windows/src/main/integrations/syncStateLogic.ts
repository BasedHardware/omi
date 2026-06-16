// Pure idempotency logic for Google sync. No IO; unit-testable.

export type SourceState = {
  lastSyncAt: number
  processedIds: string[]
}

/** Cap on retained processed IDs per source (bounded memory; old IDs age out). */
export const MAX_PROCESSED = 1000

export function emptySourceState(): SourceState {
  return { lastSyncAt: 0, processedIds: [] }
}

export function normalizeSourceState(value: unknown): SourceState {
  if (!value || typeof value !== 'object') return emptySourceState()
  const raw = value as { lastSyncAt?: unknown; processedIds?: unknown }
  const lastSyncAt =
    typeof raw.lastSyncAt === 'number' && Number.isFinite(raw.lastSyncAt) && raw.lastSyncAt > 0
      ? raw.lastSyncAt
      : 0

  if (!Array.isArray(raw.processedIds)) {
    return { lastSyncAt, processedIds: [] }
  }

  const seen = new Set<string>()
  const processedIds: string[] = []
  for (let i = raw.processedIds.length - 1; i >= 0; i--) {
    const id = raw.processedIds[i]
    if (typeof id !== 'string' || !id || seen.has(id)) continue
    processedIds.unshift(id)
    seen.add(id)
    if (seen.size >= MAX_PROCESSED) break
  }

  const bounded =
    processedIds.length > MAX_PROCESSED
      ? processedIds.slice(processedIds.length - MAX_PROCESSED)
      : processedIds
  return { lastSyncAt, processedIds: bounded }
}

/** Items whose id is NOT already in the processed set. */
export function filterNew<T extends { id: string }>(items: T[], processedIds: string[]): T[] {
  const seen = new Set(processedIds)
  return items.filter((it) => !seen.has(it.id))
}

/** Merge ids into state (dedup, newest appended last, bounded), set lastSyncAt=now. */
export function recordProcessed(state: SourceState, ids: string[], now: number): SourceState {
  const merged = [...state.processedIds]
  const have = new Set(merged)
  for (const id of ids) {
    if (!have.has(id)) {
      merged.push(id)
      have.add(id)
    }
  }
  const bounded =
    merged.length > MAX_PROCESSED ? merged.slice(merged.length - MAX_PROCESSED) : merged
  return { lastSyncAt: now, processedIds: bounded }
}
