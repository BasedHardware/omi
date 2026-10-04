// The language proactive assistants write user-visible text in. The backend stores
// one preferred language per account (/v1/users/language); every assistant whose
// output the user reads (tasks, memories, insights, goals, focus) appends
// outputLanguageInstruction() to its system prompt so a Spanish-speaking user does
// not get English tasks. English needs no instruction — the prompts are English.
import { net } from 'electron'
import { getAbortSignal, getBackendSession, getSessionEpoch } from './session'

const LANGUAGE_TTL_MS = 3_600_000
/** A failed lookup is remembered briefly so a hanging endpoint costs one timeout
 *  per minute, not one per assistant run. */
const LANGUAGE_FAILURE_TTL_MS = 60_000
const LANGUAGE_TIMEOUT_MS = 15_000

// Keyed by the session epoch (bumped by setBackendSession on every sign-in, sign-out
// and account switch), so one account's language never reaches the next account.
let langCache: { epoch: number; at: number; ttl: number; language: string | null } | null = null
// The lookup in flight for an epoch: concurrent assistants share one request.
let inFlight: { epoch: number; promise: Promise<string | null> } | null = null

/** The user's preferred language: cached 1h after a successful read, 60s after a
 *  failure. Fail-open to null (no directive) on no-session, non-OK, or any error.
 *  A null return means "no language override", i.e. English default. */
export async function getUserLanguage(now: number = Date.now()): Promise<string | null> {
  const epoch = getSessionEpoch()
  if (langCache && langCache.epoch === epoch && now - langCache.at < langCache.ttl) {
    return langCache.language
  }
  if (inFlight && inFlight.epoch === epoch) return inFlight.promise
  const session = getBackendSession()
  if (!session) return null
  const promise = fetchUserLanguage(session).then(({ language, ok }) => {
    // A lookup that finished after a session change belongs to the old account.
    if (getSessionEpoch() === epoch) {
      langCache = { epoch, at: now, ttl: ok ? LANGUAGE_TTL_MS : LANGUAGE_FAILURE_TTL_MS, language }
    }
    return language
  })
  const entry = { epoch, promise }
  inFlight = entry
  void promise.finally(() => {
    if (inFlight === entry) inFlight = null
  })
  return promise
}

async function fetchUserLanguage(session: {
  apiBase: string
  token: string
}): Promise<{ language: string | null; ok: boolean }> {
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
    if (!res.ok) return { language: null, ok: false }
    const data = (await res.json()) as { language?: string | null }
    const lang =
      typeof data.language === 'string' && data.language.trim() ? data.language.trim() : null
    return { language: lang, ok: true }
  } catch {
    return { language: null, ok: false }
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/** Test/teardown: drop the language cache and any shared in-flight lookup. */
export function resetUserLanguageCache(): void {
  langCache = null
  inFlight = null
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
