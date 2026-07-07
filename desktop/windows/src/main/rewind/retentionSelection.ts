const DAY_MS = 24 * 60 * 60 * 1000

/** Frames with ts < the returned cutoff are eligible for pruning. */
export function retentionCutoff(nowMs: number, retentionDays: number): number {
  if (retentionDays <= 0) return nowMs
  return nowMs - retentionDays * DAY_MS
}
