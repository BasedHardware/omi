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
