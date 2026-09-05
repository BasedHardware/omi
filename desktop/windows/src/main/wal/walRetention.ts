/**
 * Decides which stored recordings to release when the write-ahead log outgrows
 * its budget. Pure so the ordering rules are testable: what gets deleted first
 * when a disk is filling is exactly the kind of thing that should not be
 * decided incidentally inside an I/O loop.
 *
 * The ordering is a safety ordering, not a size one. Audio that has been
 * confirmed by the server is a cache; audio that has not is the only copy.
 */

import { isWalDeletable, type WalEntry } from '../../shared/wal'

export interface RetentionPolicy {
  /** Bytes the stored audio may occupy in total. */
  maxBytes: number
  /** Confirmed recordings older than this are released even under budget. */
  retentionDays: number
}

export const DEFAULT_RETENTION: RetentionPolicy = {
  // A day of continuous 16 kHz mono capture is about 2.7 GB, so this holds a
  // long outage without letting a broken sync fill the disk.
  maxBytes: 2 * 1024 * 1024 * 1024,
  retentionDays: 14
}

export interface RetentionDecision {
  /** Released because the server confirmed them and they aged out. */
  expired: WalEntry[]
  /** Released to get back under the size budget. */
  overBudget: WalEntry[]
  /** Kept, but the log is full and new audio may not fit. */
  atCapacity: boolean
  bytesAfter: number
}

/**
 * Chooses what to release. Only confirmed recordings are ever candidates: the
 * bytes of anything else are the only copy of that audio, so a full disk must
 * surface as a warning rather than as silent data loss.
 */
export function planRetention(
  entries: WalEntry[],
  policy: RetentionPolicy,
  nowSeconds: number
): RetentionDecision {
  const cutoff = nowSeconds - policy.retentionDays * 24 * 60 * 60
  const expired: WalEntry[] = []
  const releasable: WalEntry[] = []
  let bytes = 0

  for (const entry of entries) {
    bytes += entry.sizeBytes
    if (!isWalDeletable(entry)) continue
    if (entry.timerStart < cutoff) expired.push(entry)
    else releasable.push(entry)
  }

  let bytesAfter = bytes - expired.reduce((sum, e) => sum + e.sizeBytes, 0)
  const overBudget: WalEntry[] = []
  if (bytesAfter > policy.maxBytes) {
    // Oldest confirmed audio goes first: it is the least likely to still be
    // interesting and the most likely to have been superseded.
    const byAge = [...releasable].sort((a, b) => a.timerStart - b.timerStart)
    for (const entry of byAge) {
      if (bytesAfter <= policy.maxBytes) break
      overBudget.push(entry)
      bytesAfter -= entry.sizeBytes
    }
  }

  return {
    expired,
    overBudget,
    // Still over budget after releasing everything releasable means the rest is
    // unconfirmed audio that must not be deleted to make room.
    atCapacity: bytesAfter > policy.maxBytes,
    bytesAfter
  }
}

/** Total bytes the log is holding. */
export function totalBytes(entries: WalEntry[]): number {
  return entries.reduce((sum, entry) => sum + entry.sizeBytes, 0)
}
