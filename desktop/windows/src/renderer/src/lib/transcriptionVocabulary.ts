// Custom transcription vocabulary: names, brands, and jargon the speech model should
// expect. Stored on the account (PATCH /v1/users/transcription-preferences) — the
// backend loads it when each /v4/listen session starts and passes it to the STT
// provider as keywords, so no listen/PTT parameter is needed here. Shared with the
// macOS and mobile clients. Mac reference: SettingsContentView+Transcription.swift.
import { omiApi } from './apiClient'
import { setUserVocabulary } from './ptt/userVocabulary'

/** Backend cap (database/users.set_user_transcription_preferences). The backend and
 *  macOS put no limit on a term's length, so neither do we. */
export const MAX_VOCABULARY_TERMS = 100

/** Trim, drop empties, de-duplicate case-insensitively (first spelling wins; plain
 *  toLowerCase like the PTT keyword path, so the result never depends on the OS
 *  locale), and cap at the backend's 100-term limit. */
export function normalizeVocabulary(terms: readonly string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of terms) {
    const term = raw.replace(/\s+/g, ' ').trim()
    if (!term) continue
    const key = term.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(term)
    if (out.length === MAX_VOCABULARY_TERMS) break
  }
  return out
}

/** Split a typed entry on commas so pasting "Omi, Callie, OpenAI" adds three terms. */
export function parseVocabularyInput(input: string): string[] {
  return input.split(',')
}

export async function fetchVocabulary(): Promise<string[]> {
  const res = await omiApi.get<{ vocabulary?: unknown }>('/v1/users/transcription-preferences')
  const list = Array.isArray(res.data?.vocabulary) ? res.data.vocabulary : []
  return normalizeVocabulary(list.filter((t): t is string => typeof t === 'string'))
}

/** Save the list and, once the backend accepted it, hand it to the PTT keyword cache
 *  so the next push-to-talk turn uses the new terms without a refetch. */
export async function saveVocabulary(terms: readonly string[]): Promise<void> {
  const vocabulary = normalizeVocabulary(terms)
  await omiApi.patch('/v1/users/transcription-preferences', { vocabulary })
  setUserVocabulary(vocabulary)
}
