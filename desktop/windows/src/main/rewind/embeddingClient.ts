// Gemini embeddings, via Omi's desktop-backend proxy. Main-process twin of the
// renderer's `lib/geminiClient.ts` (same base URL, same Firebase Bearer auth —
// the backend injects the real Gemini key), and a faithful port of the macOS
// embedding client: `gemini-embedding-001`, RETRIEVAL_DOCUMENT for stored OCR
// text vs RETRIEVAL_QUERY for a search box, L2-normalized on the way out.
//
// This lives in main (not the renderer) because the indexer it feeds is a
// background job that must survive renderer navigation/reloads — same reason as
// `ipc/memoryCleanup.ts`. The Firebase token only exists in the renderer, so it
// is relayed in over IPC (see `embeddingService.configureRewindEmbedSession`).
import { net } from 'electron'
import { EMBED_DIM, EMBED_MODEL, l2Normalize } from './embedVector'

/** Gemini task types. Asymmetric on purpose: a stored passage and a search query
 *  are embedded into the same space but with different intent, which measurably
 *  improves retrieval over using one type for both. */
export type EmbedTaskType = 'RETRIEVAL_DOCUMENT' | 'RETRIEVAL_QUERY'

/** Where to reach the proxy, and who is asking. Relayed from the renderer. */
export type EmbedSession = { desktopApiBase: string; token: string }

const REQUEST_TIMEOUT_MS = 30_000
const MAX_RETRIES = 2

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

type EmbeddingResponse = { embedding?: { values?: number[] } }
type BatchEmbeddingResponse = { embeddings?: { values?: number[] }[] }

/** Body of one `embedContent` request (also the element shape of a batch). */
function requestBody(text: string, taskType: EmbedTaskType): Record<string, unknown> {
  return {
    model: `models/${EMBED_MODEL}`,
    content: { parts: [{ text }] },
    taskType
  }
}

/** Validate + normalize one raw `values` array from the API. */
function toVector(values: number[] | undefined): Float32Array | null {
  if (!values || values.length !== EMBED_DIM) return null
  return l2Normalize(Float32Array.from(values))
}

/**
 * POST to the proxy with retries on 429/503 (the same policy as the renderer's
 * Gemini client). Errors are deliberately sanitized to a status code: the proxy
 * body can echo request content and auth material, and this text ends up in logs.
 */
async function post(
  session: EmbedSession,
  method: string,
  body: unknown
): Promise<Record<string, unknown>> {
  const url = `${session.desktopApiBase}/v1/proxy/gemini/models/${EMBED_MODEL}:${method}`
  let lastError = ''
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
    try {
      // Electron's net.fetch uses Chromium's network stack (proxy/TLS aware) —
      // the path the rest of the app's main-process HTTP already takes.
      const res = await net.fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.token}` },
        body: JSON.stringify(body),
        signal: ctrl.signal
      })
      if (res.ok) return (await res.json()) as Record<string, unknown>
      if (res.status === 429 || res.status === 503) {
        lastError = `status ${res.status}`
        // No point sleeping after the last attempt — we are about to throw.
        if (attempt < MAX_RETRIES) await sleep(400 * (attempt + 1))
        continue
      }
      throw new Error(`embedding proxy request failed (status ${res.status})`)
    } catch (e) {
      // A timeout/network drop is retryable; a thrown non-retryable status is not.
      if (e instanceof Error && e.message.startsWith('embedding proxy request failed')) throw e
      lastError = `network: ${(e as Error).message}`
      if (attempt === MAX_RETRIES) break
      await sleep(400 * (attempt + 1))
    } finally {
      clearTimeout(timer)
    }
  }
  throw new Error(`embedding proxy request failed after retries (${lastError})`)
}

/** Embed one text (used for search queries). Throws on failure. */
export async function embedOne(
  session: EmbedSession,
  text: string,
  taskType: EmbedTaskType
): Promise<Float32Array> {
  const json = (await post(
    session,
    'embedContent',
    requestBody(text, taskType)
  )) as EmbeddingResponse
  const vec = toVector(json.embedding?.values)
  if (!vec) throw new Error('embedding proxy returned no usable vector')
  return vec
}

/**
 * The provider's hard limit on one `batchEmbedContents` body. Verified live: 101
 * requests is a `400 INVALID_ARGUMENT` that fails the entire batch. Enforced here
 * as well as at the queue (`EMBED_BATCH_SIZE`) so no future caller can put an
 * over-limit body on the wire, whatever it thinks its batch size is.
 */
const MAX_BATCH_REQUESTS = 100

/**
 * Embed a batch of texts. Returns one entry per input, in order; an entry is null
 * when the API omitted it or returned a wrong-dimension vector, so one bad item
 * can't discard the whole batch. Throws only when a request itself fails.
 *
 * Chunked at the API's 100-request ceiling, sequentially — a caller with 250
 * texts gets 3 round trips, not one guaranteed 400.
 */
export async function embedBatch(
  session: EmbedSession,
  texts: string[],
  taskType: EmbedTaskType
): Promise<(Float32Array | null)[]> {
  if (texts.length === 0) return []
  const out: (Float32Array | null)[] = []
  for (let i = 0; i < texts.length; i += MAX_BATCH_REQUESTS) {
    const chunk = texts.slice(i, i + MAX_BATCH_REQUESTS)
    const json = (await post(session, 'batchEmbedContents', {
      requests: chunk.map((t) => requestBody(t, taskType))
    })) as BatchEmbeddingResponse
    const embeddings = json.embeddings ?? []
    for (let j = 0; j < chunk.length; j++) out.push(toVector(embeddings[j]?.values))
  }
  return out
}
