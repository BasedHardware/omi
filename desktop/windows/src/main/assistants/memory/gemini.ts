// The Gemini vision call for memory extraction — single-shot (image + prompt →
// structured JSON), NOT a tool loop. Byte-for-byte the same transport machinery
// as focus/gemini.ts (the retry/timeout/abort composition is identical); only the
// response schema, the parser, and the return type differ.
//
// It goes through the Rust desktop backend's proxy, never Gemini directly: the
// API key lives on the server and never touches the device.
import { net } from 'electron'
import { getAbortSignal, type BackendSession } from '../core/session'
import {
  MEMORY_RESPONSE_SCHEMA,
  parseMemoryExtraction,
  type MemoryExtractionResult
} from './models'

const MODEL = 'gemini-2.5-flash'
const REQUEST_TIMEOUT_MS = 30_000
/** 3 attempts total. Mac's backoff, exactly: 2s then 8s. */
const RETRY_DELAYS_MS = [2_000, 8_000]

/** Carries the status only — never a response body (it can echo the prompt,
 *  which carries the screen contents). */
export class GeminiHttpError extends Error {
  constructor(readonly status: number) {
    super(`gemini proxy HTTP ${status}`)
    this.name = 'GeminiHttpError'
  }
}

/** 5xx and 429 are worth another attempt; a 400/401/403 will fail identically
 *  three times in a row, and retrying a paywall/auth rejection just burns the
 *  user's battery. */
function isTransient(e: unknown): boolean {
  if (e instanceof GeminiHttpError) return e.status === 429 || e.status >= 500
  // A per-request TIMEOUT (surfaced as 'TimeoutError') and a bare network error
  // (TypeError from net.fetch) are both worth retrying. Only a genuine session
  // sign-out — the external AbortSignal firing, surfaced as 'AbortError' — is
  // terminal: the token is dead, so retrying is pointless.
  return !(e instanceof Error && e.name === 'AbortError')
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('aborted', 'AbortError'))
    const t = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(t)
        reject(new DOMException('aborted', 'AbortError'))
      },
      { once: true }
    )
  })
}

/** Run `fn` with a per-request timeout, composed with an optional external
 *  (session) abort signal. A timeout surfaces as a 'TimeoutError' (retryable),
 *  while the external signal surfaces as an 'AbortError' (a session sign-out —
 *  terminal). `fn` sees a single composed signal and doesn't care which fired. */
async function withTimeout<T>(
  ms: number,
  fn: (signal: AbortSignal) => Promise<T>,
  external?: AbortSignal
): Promise<T> {
  const ctrl = new AbortController()
  let timedOut = false
  const onAbort = (): void => ctrl.abort(external?.reason)
  const timer = setTimeout(() => {
    timedOut = true
    ctrl.abort(new DOMException('request timed out', 'TimeoutError'))
  }, ms)
  if (external?.aborted) ctrl.abort(external.reason)
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    return await fn(ctrl.signal)
  } catch (e) {
    if (timedOut) throw new DOMException('request timed out', 'TimeoutError')
    throw e
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/** The text of the first candidate's first text part, '' if the model returned
 *  nothing usable (a safety block, an empty candidate list). */
function extractText(json: unknown): string {
  const parts = (
    json as {
      candidates?: { content?: { parts?: { text?: string }[] } }[]
    }
  )?.candidates?.[0]?.content?.parts
  if (!Array.isArray(parts)) return ''
  return parts
    .map((p) => p.text ?? '')
    .join('')
    .trim()
}

async function attempt(
  session: BackendSession,
  systemPrompt: string,
  prompt: string,
  imageBase64: string,
  external?: AbortSignal
): Promise<string> {
  return withTimeout(
    REQUEST_TIMEOUT_MS,
    async (signal) => {
      const res = await net.fetch(
        `${session.desktopApiBase}/v1/proxy/gemini/models/${MODEL}:generateContent`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${session.token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            contents: [
              {
                role: 'user',
                parts: [
                  { text: prompt },
                  // The TRUE encoding. Mac hardcodes `image/webp` here whatever
                  // the bytes actually are — a Mac bug we are not porting.
                  { inlineData: { mimeType: 'image/jpeg', data: imageBase64 } }
                ]
              }
            ],
            systemInstruction: { parts: [{ text: systemPrompt }] },
            generationConfig: {
              responseMimeType: 'application/json',
              responseSchema: MEMORY_RESPONSE_SCHEMA,
              // Flash's minimum (Mac passes 0 for memory extraction). No reasoning
              // budget — it needs to be cheap enough to run every 10 minutes all day.
              thinkingConfig: { thinkingBudget: 0 }
            }
          }),
          signal
        }
      )
      if (!res.ok) throw new GeminiHttpError(res.status)
      return extractText(await res.json())
    },
    external
  )
}

/**
 * Extract memories from one screenshot. Returns null when the model answered with
 * something we cannot parse (see models.ts) — that is "no extraction", not an
 * error, and must not trip the caller's error handling.
 *
 * Throws on transport/HTTP failure after all attempts are spent.
 */
export async function extractMemory(
  session: BackendSession,
  systemPrompt: string,
  prompt: string,
  imageBase64: string
): Promise<MemoryExtractionResult | null> {
  // The session's signal: a sign-out or token refresh kills the request in flight
  // instead of leaving it running for 30s with a dead token.
  const external = getAbortSignal()
  let lastError: unknown

  for (let i = 0; i <= RETRY_DELAYS_MS.length; i++) {
    try {
      const text = await attempt(session, systemPrompt, prompt, imageBase64, external)
      if (!text) return null
      return parseMemoryExtraction(text)
    } catch (e) {
      lastError = e
      if (i === RETRY_DELAYS_MS.length || !isTransient(e)) break
      await sleep(RETRY_DELAYS_MS[i], external)
    }
  }
  throw lastError
}
