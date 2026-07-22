// Reconstruct the assistant reply from Omi's /v2/messages SSE response when it's
// consumed as one buffered string (not streamed). Mirrors useChat's streaming
// parse: each line is `data: <chunk>` (drop the prefix), `done:`/`message:` are
// terminal/side-message base64 frames (drop them — never reply text), `think:`
// payloads are ephemeral status events (drop them), and reply newlines are
// encoded as the literal token __CRLF__. Pure — no imports — so it's unit
// testable without dragging in firebase/apiClient.
export function parseMessagesSse(raw: string): string {
  const out: string[] = []
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith('done:') || line.startsWith('message:')) continue
    const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
    if (content.startsWith('think:')) continue
    out.push(content)
  }
  return out.join('').replace(/__CRLF__/g, '\n')
}

/**
 * The assistant message carried by the terminal `done:` SSE frame. Unlike the
 * streamed `data:` chunks, the backend (routers/chat.py `generate_stream`)
 * base64-encodes a full ResponseMessage JSON here whose `text` has the `[n]`
 * citation markers stripped, and which carries the SERVER message id plus the
 * cited conversations / chart / NPS metadata. Only the fields Windows consumes
 * are typed. Dropping this frame is why literal `[1]` markers used to leak into
 * the reply and why rating/report/share had no server id to key off of (C4).
 */
export type DoneMessage = {
  /** Server (Firestore) message id — the handle for rating / report / share. */
  id?: string
  /** Final, citation-stripped reply text. Replaces the accumulated stream text. */
  text: string
  /** Conversations the answer cited (wire field `memories`). */
  citations: { id: string; title: string; emoji?: string }[]
  /** Inline chart payload, if any (opaque — no chart UI on Windows yet). */
  chartData?: unknown
  /** Whether the backend asked to prompt for an NPS rating this turn. */
  askForNps: boolean
}

// base64 → UTF-8 text. atob yields a binary (latin1) string, so multibyte JSON
// would be mangled without re-decoding the bytes as UTF-8.
function decodeBase64Utf8(b64: string): string {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

/**
 * Parse a single terminal `done:` SSE line into the final assistant message, or
 * null if the line isn't a `done:` frame or its base64 JSON payload can't be
 * decoded (a malformed frame must never throw and abort the stream teardown).
 */
export function parseDoneMessage(line: string): DoneMessage | null {
  if (!line.startsWith('done:')) return null
  const b64 = line.slice(5).trim()
  if (!b64) return null
  let raw: {
    id?: unknown
    text?: unknown
    memories?: unknown
    chart_data?: unknown
    ask_for_nps?: unknown
  }
  try {
    raw = JSON.parse(decodeBase64Utf8(b64))
  } catch {
    return null
  }
  const citations = Array.isArray(raw.memories)
    ? raw.memories.flatMap((m) => {
        const c = m as { id?: unknown; structured?: { title?: unknown; emoji?: unknown } }
        if (typeof c?.id !== 'string') return []
        return [
          {
            id: c.id,
            title: typeof c.structured?.title === 'string' ? c.structured.title : '',
            emoji: typeof c.structured?.emoji === 'string' ? c.structured.emoji : undefined
          }
        ]
      })
    : []
  return {
    id: typeof raw.id === 'string' ? raw.id : undefined,
    text: typeof raw.text === 'string' ? raw.text : '',
    citations,
    chartData: raw.chart_data ?? undefined,
    askForNps: raw.ask_for_nps === true
  }
}
