// Default language list offered by the startup wizard and Settings. Codes are
// stored verbatim in preferences and passed to the Omi v4/listen URL. English is
// the default selection.

export type Language = { code: string; label: string }

export const LANGUAGES: Language[] = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'it', label: 'Italian' },
  { code: 'nl', label: 'Dutch' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'zh', label: 'Chinese' },
  { code: 'hi', label: 'Hindi' },
  { code: 'ru', label: 'Russian' },
  // Sentinel for an unrecognized free-text choice; passed to v4/listen verbatim
  // as a multilingual hint. Kept in the list so the Settings dropdown can display
  // a resolved-to-'multi' selection instead of rendering blank.
  { code: 'multi', label: 'Other / Multilingual' }
]

export const DEFAULT_LANGUAGE = 'en'

// Fallback code for free-text input we can't map to a known language. 'multi'
// is a reasonable multilingual signal to the transcription backend.
export const FALLBACK_LANGUAGE = 'multi'

export function languageLabel(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.label ?? code
}

// Common autonyms and alternate spellings users are likely to type in the
// onboarding free-text box, mapped to the ISO 639-1 codes the rest of the app
// (v4/listen URL, PATCH /v1/users/language, Settings dropdown) expects.
const ALIASES: Record<string, string> = {
  english: 'en',
  spanish: 'es',
  espanol: 'es',
  español: 'es',
  castellano: 'es',
  french: 'fr',
  francais: 'fr',
  français: 'fr',
  german: 'de',
  deutsch: 'de',
  portuguese: 'pt',
  portugues: 'pt',
  português: 'pt',
  italian: 'it',
  italiano: 'it',
  dutch: 'nl',
  nederlands: 'nl',
  japanese: 'ja',
  日本語: 'ja',
  nihongo: 'ja',
  korean: 'ko',
  한국어: 'ko',
  chinese: 'zh',
  mandarin: 'zh',
  中文: 'zh',
  普通话: 'zh',
  hindi: 'hi',
  हिन्दी: 'hi',
  russian: 'ru',
  русский: 'ru'
}

/**
 * Normalize free-text or code input to an ISO 639-1 language code the app can
 * use. Resolution order: exact known code → label match → alias map. Unknown
 * input falls back to {@link FALLBACK_LANGUAGE} ('multi') rather than passing an
 * untranslated language name (e.g. "Spanish") downstream, which the transcription
 * backend can't interpret. Empty input falls back to the default ('en').
 */
export function resolveLanguageCode(input: string): string {
  const raw = (input ?? '').trim()
  if (raw.length === 0) return DEFAULT_LANGUAGE
  const normalized = raw.toLowerCase()
  // Already a known code (covers 'multi' too).
  if (LANGUAGES.some((l) => l.code === normalized)) return normalized
  // Matches a label, e.g. "Spanish".
  const byLabel = LANGUAGES.find((l) => l.label.toLowerCase() === normalized)
  if (byLabel) return byLabel.code
  // Autonym / alternate spelling. Try both the lowercased and raw forms so
  // non-Latin scripts (which have no case) still match.
  return ALIASES[normalized] ?? ALIASES[raw] ?? FALLBACK_LANGUAGE
}
