// The language proactive assistants write user-visible text in. The backend stores
// one preferred language per account (/v1/users/language); every assistant whose
// output the user reads (tasks, memories, insights, goals, focus) appends
// outputLanguageInstruction() to its system prompt so a Spanish-speaking user does
// not get English tasks. English needs no instruction — the prompts are English.
// Mirrors macOS AssistantOutputLanguage.swift.
import { net } from 'electron'
import { getAbortSignal, getBackendSession } from './session'

const LANGUAGE_TTL_MS = 3_600_000
const LANGUAGE_TIMEOUT_MS = 15_000

let langCache: { at: number; language: string | null } | null = null

/** The user's preferred language, cached 1h. Fail-open to null (no directive) on
 *  no-session, non-OK, or any error — exactly Mac's fallback (empty/"en" → nil).
 *  A null return means "no language override", i.e. English default. */
export async function getUserLanguage(now: number = Date.now()): Promise<string | null> {
  if (langCache && now - langCache.at < LANGUAGE_TTL_MS) return langCache.language
  const session = getBackendSession()
  if (!session) return null
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const onAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), LANGUAGE_TIMEOUT_MS)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    const res = await net.fetch(`${session.apiBase}/v1/users/language`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${session.token}` },
      signal: ctrl.signal
    })
    if (!res.ok) return null
    const data = (await res.json()) as { language?: string | null }
    const lang =
      typeof data.language === 'string' && data.language.trim() ? data.language.trim() : null
    // Cache only a successful read; a failure retries next call rather than
    // caching "unknown" for an hour.
    langCache = { at: now, language: lang }
    return lang
  } catch {
    return null
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/** Test/teardown: drop the language cache. */
export function resetUserLanguageCache(): void {
  langCache = null
}

const LANGUAGE_NAMES: Record<string, string> = {
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  pt: 'Portuguese',
  it: 'Italian',
  nl: 'Dutch',
  ja: 'Japanese',
  ko: 'Korean',
  zh: 'Chinese',
  hi: 'Hindi',
  ru: 'Russian'
}

/** Prompt suffix for a preferred language, or null when none is needed (unset,
 *  English, or the 'multi' transcription sentinel). */
export function outputLanguageInstruction(code: string | null | undefined): string | null {
  const trimmed = code?.trim()
  if (!trimmed) return null
  const base = trimmed.split(/[-_]/)[0].toLowerCase()
  if (base === 'en' || base === 'multi') return null
  const name = LANGUAGE_NAMES[base] ?? trimmed
  return (
    `IMPORTANT: Write all user-visible text (titles, descriptions, memories, advice) in ${name} (${trimmed}), ` +
    `the user's preferred language. Keep names, app names, and quoted on-screen text as they appear.`
  )
}

/** `systemPrompt` plus the preferred-language instruction, when one applies.
 *  Never throws: a language lookup must not cost the user a task or memory. */
export async function withOutputLanguage(systemPrompt: string): Promise<string> {
  try {
    const instruction = outputLanguageInstruction(await getUserLanguage())
    return instruction ? `${systemPrompt}\n\n${instruction}` : systemPrompt
  } catch {
    return systemPrompt
  }
}
