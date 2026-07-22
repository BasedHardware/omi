// The user's account-level custom transcription vocabulary — Source 1 of PTT
// keyword boosting (see vocabulary.ts). On macOS this is
// AssistantSettings.shared.effectiveVocabulary, the FIRST source fed into the
// KeywordCollector so custom terms take priority over on-screen OCR. Windows has
// no local vocabulary preference (the TranscriptionTab control is unbuilt); the
// list is set on Mac/mobile and synced to the backend, so we fetch it from
// GET /v1/users/transcription-preferences and cache it here.
//
// Never blocks the PTT hot path: collectPttKeywords reads getUserVocabulary()
// synchronously (a cache read), exactly like macOS reads an already-synced local
// setting. refreshUserVocabulary() is a fire-and-forget background warm — a cold
// cache simply contributes nothing (degrading to the OCR/frame sources) rather
// than stalling a turn on the network.
//
// Cache discipline mirrors voice/aboutUser.ts: keyed by uid, dropped on sign-out,
// and a build whose account switched away mid-fetch is discarded (never filed
// under the old uid) so one account's vocabulary can never leak to another.

import { auth } from '../firebase'
import { omiApi } from '../apiClient'

/** Fetch the account's custom vocabulary from the backend. Any failure → [] (the
 *  caller degrades to the OCR/frame sources). Owns its own fetch: there is no
 *  synchronous Windows preference for this list. */
async function fetchUserVocabulary(): Promise<string[]> {
  try {
    const res = await omiApi.get('/v1/users/transcription-preferences')
    const vocab = (res.data as { vocabulary?: unknown })?.vocabulary
    if (!Array.isArray(vocab)) return []
    return vocab.filter((t): t is string => typeof t === 'string')
  } catch {
    return []
  }
}

// ── Cache (read synchronously in the PTT hot path, refreshed off it) ───────────
// Keyed by uid so one account's vocabulary can never leak across a switch.

let cached: { uid: string; vocabulary: string[] } | null = null
let inFlight: Promise<void> | null = null
// The uid the in-flight fetch was started for (see refreshUserVocabulary).
let inFlightUid = ''
// Bumped by resetUserVocabulary so an in-flight fetch from before the reset
// (e.g. the previous account's) can never land in the cache afterwards.
let generation = 0

/** The cached vocabulary for the current user, or [] when nothing has been synced
 *  for them yet (in which case the collector simply omits Source 1 — never a
 *  stale/other-user list and never a blocking fetch). Safe to call on the PTT hot
 *  path: it is a synchronous cache read. */
export function getUserVocabulary(): string[] {
  const uid = auth.currentUser?.uid ?? ''
  return cached && cached.uid === uid ? cached.vocabulary : []
}

/** Refresh the cache in the background (fire-and-forget, deduped per-account).
 *  Warmed at sign-in (App.tsx). THIS session uses whatever is cached; the next
 *  hold gets the fresh list — a slightly stale vocabulary is acceptable, a slow
 *  key-down is not. */
export function refreshUserVocabulary(): void {
  const uid = auth.currentUser?.uid ?? ''
  // Dedupe only against a fetch for the SAME account — an account switch must be
  // able to start its own fetch even while the previous one is still in flight.
  if (inFlight && inFlightUid === uid) return
  const gen = generation
  inFlightUid = uid
  const build = fetchUserVocabulary()
    .then((vocabulary) => {
      // Cache only if that account is still the signed-in one. The fetch ran
      // against whatever token was current when it landed, so an account switch
      // mid-fetch would otherwise file the NEW user's vocabulary under the OLD
      // uid — and serve it back if the old account returned.
      if (gen === generation && (auth.currentUser?.uid ?? '') === uid) cached = { uid, vocabulary }
    })
    .catch(() => {
      /* best-effort: keep whatever list we already had */
    })
    .finally(() => {
      if (inFlight === build) inFlight = null
    })
  inFlight = build
}

/** Await the in-flight refresh — tests only (production never blocks on this). */
export function whenUserVocabularySettled(): Promise<void> {
  return inFlight ?? Promise.resolve()
}

/** Drop the cached vocabulary and abandon any in-flight fetch. Called on sign-out
 *  (App.tsx) so a list can never outlive the account it was fetched for, and by
 *  tests to reset module state. */
export function resetUserVocabulary(): void {
  cached = null
  inFlight = null
  inFlightUid = ''
  generation++
}
