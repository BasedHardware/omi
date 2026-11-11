// Stale-while-revalidate cache for the Hub stat ribbon's four counts, so a cold
// launch renders the LAST-KNOWN numbers immediately instead of four em-dashes
// while each count's fetch is in flight. The live values (useHubStats) still win
// the moment they land and overwrite the cache — this only fills the cold gap.
//
// CROSS-ACCOUNT GUARD (the reason this isn't a plain blob in localStorage): the
// counts belong to the account that produced them. If a different user signs in
// on the same machine, they must NOT see the previous account's numbers — the
// same cross-account-leak class the BYOK key / onboarding-count stores hit. The
// blob therefore stamps the owning uid; a read under any other uid returns the
// unknown (em-dash) state, and a write under a new uid discards the prior owner's
// counts. The uid stamp is the guard (mirroring onboardingImportCounts), so this
// key deliberately does NOT need to be in authTeardown's wipe list. The pure core
// (readStats / mergeStats / overlay) is exported and unit-tested against exactly
// the account-switch scenario.
import type { HubStatCounts } from './HubStatRibbon'

const KEY = 'hubStatCounts'

// The stored shape: the ribbon's four counts + the conversations "+" flag, plus
// the owning uid. A count is `number | null` — null keeps the "unknown" (em-dash)
// meaning end to end, never a fabricated 0.
type Stored = {
  uid: string | null
  conversations: number | null
  conversationsAtLeast: boolean
  tasks: number | null
  memories: number | null
  screenshots: number | null
}

const UNKNOWN: HubStatCounts = {
  conversations: null,
  conversationsAtLeast: false,
  tasks: null,
  memories: null,
  screenshots: null
}

// A cached count is trustworthy only as a non-negative integer; anything else
// (negative, NaN, malformed) becomes "unknown" rather than a wrong number.
function coerceCount(v: unknown): number | null {
  if (v === null || v === undefined) return null
  const n = Number(v)
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null
}

/**
 * Pure read: the counts a given uid is allowed to see from a stored blob. Returns
 * the all-unknown state when the blob is missing, unparseable, or was written by a
 * DIFFERENT uid (the cross-account guard) — never the other account's numbers.
 */
export function readStats(raw: string | null, uid: string | null): HubStatCounts {
  if (!raw) return { ...UNKNOWN }
  let parsed: Partial<Stored>
  try {
    parsed = JSON.parse(raw) as Partial<Stored>
  } catch {
    return { ...UNKNOWN }
  }
  // The guard: counts are only visible to the account that wrote them.
  if (!parsed || parsed.uid !== uid) return { ...UNKNOWN }
  return {
    conversations: coerceCount(parsed.conversations),
    conversationsAtLeast: parsed.conversationsAtLeast === true,
    tasks: coerceCount(parsed.tasks),
    memories: coerceCount(parsed.memories),
    screenshots: coerceCount(parsed.screenshots)
  }
}

/**
 * Pure write: the next stored blob after folding the KNOWN (non-null) fields of
 * `fresh` onto what `uid` already had. A still-loading field (null in `fresh`)
 * keeps its cached value rather than clobbering it — so the cache always holds the
 * last-known-good number per cell, independently. If the blob currently belongs to
 * another uid (or none), the prior counts are dropped (readStats returns unknown),
 * so a stale tally can never survive an account switch.
 */
export function mergeStats(raw: string | null, uid: string | null, fresh: HubStatCounts): string {
  const base = readStats(raw, uid) // unknown if the blob belongs to a different uid
  // The conversation count and its "+" flag move together: only overwrite the pair
  // when the fresh count is actually known, so the flag can't desync from the number.
  const conversationsKnown = fresh.conversations !== null
  const next: Stored = {
    uid,
    conversations: conversationsKnown ? fresh.conversations : base.conversations,
    conversationsAtLeast: conversationsKnown
      ? fresh.conversationsAtLeast
      : base.conversationsAtLeast,
    tasks: fresh.tasks ?? base.tasks,
    memories: fresh.memories ?? base.memories,
    screenshots: fresh.screenshots ?? base.screenshots
  }
  return JSON.stringify(next)
}

/**
 * Pure display merge: the live counts win wherever they are known; the cached
 * counts fill only the cells the live fetch hasn't resolved yet. This is what
 * produces the stale-while-revalidate render — cached now, fresh as it lands.
 */
export function overlay(cached: HubStatCounts, live: HubStatCounts): HubStatCounts {
  const conversationsKnown = live.conversations !== null
  return {
    conversations: conversationsKnown ? live.conversations : cached.conversations,
    conversationsAtLeast: conversationsKnown
      ? live.conversationsAtLeast
      : cached.conversationsAtLeast,
    tasks: live.tasks ?? cached.tasks,
    memories: live.memories ?? cached.memories,
    screenshots: live.screenshots ?? cached.screenshots
  }
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
    /* quota / privacy mode — the cache is a cosmetic convenience, safe to drop */
  }
}

/** The last-known counts the signed-in `uid` is allowed to see (unknown for any other account). */
export function getCachedHubStats(uid: string | null): HubStatCounts {
  return readStats(safeGet(), uid)
}

/** Record the known cells of `fresh` for `uid`, discarding any other account's tally. */
export function persistHubStats(uid: string | null, fresh: HubStatCounts): void {
  if (!uid) return // nothing to cache for a signed-out reader
  // Don't stamp an all-unknown blob (e.g. the first render before any fetch lands).
  const nothingKnown =
    fresh.conversations === null &&
    fresh.tasks === null &&
    fresh.memories === null &&
    fresh.screenshots === null
  if (nothingKnown) return
  safeSet(mergeStats(safeGet(), uid, fresh))
}
