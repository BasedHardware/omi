// Custom transcription vocabulary: names, brands, and jargon the speech model should
// expect. Stored on the account (PATCH /v1/users/transcription-preferences) — the
// backend loads it when each /v4/listen session starts and passes it to the STT
// provider as keywords, so no listen/PTT parameter is needed here. Shared with the
// macOS and mobile clients. Mac reference: SettingsContentView+Transcription.swift.
import { omiApi } from './apiClient'

/** Backend cap (database/users.set_user_transcription_preferences). */
export const MAX_VOCABULARY_TERMS = 100
export const MAX_VOCABULARY_TERM_LENGTH = 60

/** Trim, drop empties and over-long terms, de-duplicate case-insensitively (first
 *  spelling wins), and cap at the backend's 100-term limit. */
export function normalizeVocabulary(terms: readonly string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of terms) {
    const term = raw.replace(/\s+/g, ' ').trim()
    if (!term || term.length > MAX_VOCABULARY_TERM_LENGTH) continue
    const key = term.toLocaleLowerCase()
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

export async function saveVocabulary(terms: readonly string[]): Promise<void> {
  await omiApi.patch('/v1/users/transcription-preferences', {
    vocabulary: normalizeVocabulary(terms)
  })
}
