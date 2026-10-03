// Custom transcription vocabulary — mobile (custom_vocabulary_page) and macOS
// (SettingsContentView+Transcription "Custom Vocabulary") parity.
//
// The list is account-level state on the backend
// (GET/PATCH /v1/users/transcription-preferences → `vocabulary`) and is consumed
// in two places, neither of which needs a local preference:
//  - the ambient /v4/listen socket: the backend's listen bootstrap reads the
//    account's vocabulary and forwards it as Deepgram keyterms
//    (backend/utils/listen_session_bootstrap.py);
//  - push-to-talk: ptt/userVocabulary.ts caches the same list as Source 1 of
//    keyword boosting, so after a save we refresh that cache to make the new
//    terms take effect on the next hold without a restart.
//
// Pure list rules live here so they're unit-testable: trim, comma-split (Mac
// accepts "a, b, c" in one submit), case-insensitive dedupe, and the backend's
// hard cap of 100 terms (database/users.py slices `vocabulary[:100]` — anything
// past that is silently dropped, so the client refuses it up front instead).

import { omiApi } from './apiClient'
import { refreshUserVocabulary } from './ptt/userVocabulary'

/** Backend cap: set_user_transcription_preferences stores vocabulary[:100]. */
export const VOCABULARY_LIMIT = 100

/** Per-term cap: keeps a pasted paragraph from becoming one "term". Deepgram
 *  keyterms are short phrases; this is a client sanity bound, not a wire limit. */
export const VOCABULARY_TERM_MAX_CHARS = 60

export type AddTermsResult = {
  terms: string[]
  added: string[]
  /** Terms skipped because they already exist (case-insensitive). */
  duplicates: string[]
  /** Terms skipped because the list was full. */
  overflow: string[]
  /** Terms rejected because they exceed the per-term character limit. */
  tooLong: string[]
}

/** Split a submission into candidate terms: comma-separated, trimmed, non-empty. */
export function parseVocabularyInput(raw: string): string[] {
  return raw
    .split(',')
    .map((t) => t.trim().replace(/\s+/g, ' '))
    .filter((t) => t.length > 0)
}

/** Add one submission to the list. Dedupe is case-insensitive against both the
 *  existing list and earlier candidates in the same submission; the first
 *  spelling wins (Mac keeps the user's original casing). Never exceeds the cap. */
export function addVocabularyTerms(existing: string[], raw: string): AddTermsResult {
  const seen = new Set(existing.map((t) => t.toLowerCase()))
  const terms = [...existing]
  const added: string[] = []
  const duplicates: string[] = []
  const overflow: string[] = []
  const tooLong: string[] = []
  for (const candidate of parseVocabularyInput(raw)) {
    if (candidate.length > VOCABULARY_TERM_MAX_CHARS) {
      tooLong.push(candidate)
      continue
    }
    const key = candidate.toLowerCase()
    if (seen.has(key)) {
      duplicates.push(candidate)
      continue
    }
    if (terms.length >= VOCABULARY_LIMIT) {
      overflow.push(candidate)
      continue
    }
    seen.add(key)
    terms.push(candidate)
    added.push(candidate)
  }
  return { terms, added, duplicates, overflow, tooLong }
}

/** Remove one term (exact match — the chip carries the stored spelling). */
export function removeVocabularyTerm(existing: string[], term: string): string[] {
  return existing.filter((t) => t !== term)
}

/** The account's current list. A missing/malformed field reads as [] (an account
 *  that never set one) — callers must not treat that as an error. */
export async function fetchTranscriptionVocabulary(): Promise<string[]> {
  const res = await omiApi.get('/v1/users/transcription-preferences')
  const vocab = (res.data as { vocabulary?: unknown } | undefined)?.vocabulary
  if (!Array.isArray(vocab)) return []
  return vocab.filter((t): t is string => typeof t === 'string' && t.trim().length > 0)
}

/** Replace the account's list (the endpoint takes the whole array, not a delta),
 *  then warm the PTT keyword cache so the change is live on the next hold. The
 *  ambient listen socket reads the backend copy at session start on its own. */
export async function saveTranscriptionVocabulary(terms: string[]): Promise<void> {
  await omiApi.patch('/v1/users/transcription-preferences', {
    vocabulary: terms.slice(0, VOCABULARY_LIMIT)
  })
  refreshUserVocabulary({ force: true })
}
