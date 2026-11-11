// Per-account cache of how many memories the onboarding DataSources step imported
// from each memory-log source (ChatGPT / Claude), so a connected row can show
// "N memories" and stay collapsed after a successful import. macOS keeps the same
// tally in UserDefaults.
//
// CROSS-ACCOUNT GUARD (the reason this isn't a plain number in localStorage): a
// cached count belongs to the account that imported those memories. If a different
// user signs in on the same machine, they must NOT inherit the previous user's
// tally — that would leak "you imported 14 ChatGPT memories" across accounts, the
// same cross-account-leak class the BYOK key store hit. The blob therefore stamps
// the owning uid; a read under any other uid returns zero, and a write under a new
// uid discards the prior owner's counts. The pure core (readCounts / mergeCounts)
// is exported and unit-tested against exactly this account-switch scenario.
import type { MemorySource } from './memoryExtract'

const KEY = 'onboardingMemoryLogImportCounts'

export type ImportCounts = { chatgpt: number; claude: number }

const EMPTY: ImportCounts = { chatgpt: 0, claude: 0 }

type Stored = { uid: string | null; chatgpt: number; claude: number }

function coerceCount(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}

/**
 * Pure read: resolve the counts a given uid is allowed to see from a stored blob.
 * Returns zeros when the blob is missing, unparseable, or was written by a
 * DIFFERENT uid (the cross-account guard) — never the other account's numbers.
 */
export function readCounts(raw: string | null, uid: string | null): ImportCounts {
  if (!raw) return { ...EMPTY }
  let parsed: Partial<Stored>
  try {
    parsed = JSON.parse(raw) as Partial<Stored>
  } catch {
    return { ...EMPTY }
  }
  // The guard: a tally is only visible to the account that wrote it.
  if (!parsed || parsed.uid !== uid) return { ...EMPTY }
  return { chatgpt: coerceCount(parsed.chatgpt), claude: coerceCount(parsed.claude) }
}

/**
 * Pure write: produce the next stored blob after setting `source`'s count for
 * `uid`. If the blob currently belongs to another uid (or none), the prior
 * counts are dropped — the new owner starts from zero and only their import is
 * recorded — so a stale tally can never survive an account switch.
 */
export function mergeCounts(
  raw: string | null,
  uid: string | null,
  source: MemorySource,
  count: number
): string {
  const base = readCounts(raw, uid) // zeros if the blob belongs to a different uid
  const next: Stored = { uid, chatgpt: base.chatgpt, claude: base.claude }
  next[source] = coerceCount(count)
  return JSON.stringify(next)
}

function safeGet(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function safeSet(value: string): void {
  try {
    localStorage.setItem(KEY, value)
  } catch {
    /* quota / privacy mode — the count is a cosmetic convenience, safe to drop */
  }
}

/** Counts the signed-in `uid` is allowed to see (zeros for any other account). */
export function getImportedCounts(uid: string | null): ImportCounts {
  return readCounts(safeGet(), uid)
}

/** Record `source`'s imported count for `uid`, discarding any other account's tally. */
export function setImportedCount(uid: string | null, source: MemorySource, count: number): void {
  safeSet(mergeCounts(safeGet(), uid, source, count))
}
