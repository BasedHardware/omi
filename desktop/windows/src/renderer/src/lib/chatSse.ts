/**
 * Pure utilities for parsing the Omi /v2/messages SSE stream.
 * No React, no Firebase — safe to import in unit tests.
 */

export type ChatCitation = {
  id: string
  title: string
  emoji?: string
  created_at?: string
  /** Short preview text from the conversation overview, if the backend returned it. */
  preview?: string
}

/**
 * Parse a `done:` SSE line from the Omi /v2/messages endpoint.
 * Extracts citation metadata only — the `text` field inside the payload is
 * intentionally ignored. Streaming `data:` chunks decoded by the browser's
 * native UTF-8 layer are the authoritative display text; using the
 * base64-decoded `done:` text caused emoji garbling on some builds.
 */
export function parseDonePayload(line: string): ChatCitation[] {
  try {
    const b64 = (line.startsWith('done:') ? line.slice('done:'.length) : line).trim()
    if (!b64) return []
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    const json = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>
    const list = (json.memories ?? json.citations ?? json.sources ?? []) as unknown[]
    return (Array.isArray(list) ? list : [])
      .filter((m): m is Record<string, unknown> => !!m && typeof m === 'object')
      .map((m) => {
        const structured = m.structured as Record<string, unknown> | undefined
        const id = (m.id ?? m.memory_id ?? m.conversation_id ?? '') as string
        const rawTitle = (m.title ?? structured?.title ?? null) as string | null
        const title = rawTitle?.trim() || 'Conversation source'
        const emoji = (m.emoji ?? structured?.emoji ?? undefined) as string | undefined
        const created_at = (m.created_at ?? undefined) as string | undefined
        const rawPreview = (structured?.overview ?? m.overview ?? m.text ?? m.content ?? null) as string | null
        const preview = rawPreview?.trim() ? rawPreview.trim().slice(0, 120) : undefined
        return { id, title, emoji: emoji || undefined, created_at, preview }
      })
      .filter((c) => !!c.id)
  } catch {
    return []
  }
}

/**
 * Parse a single SSE line from the Omi streaming response.
 * Returns the decoded text chunk to append, or null if the line should be skipped.
 * Handles `data:`, `think:`, `done:` prefixes and `__CRLF__` tokens.
 */
export function parseSseLine(line: string): string | null {
  if (!line || line.startsWith('done:') || line.startsWith('think:')) return null
  const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
  if (content.startsWith('think:')) return null
  const chunk = content.replace(/__CRLF__/g, '\n')
  return chunk || null
}
