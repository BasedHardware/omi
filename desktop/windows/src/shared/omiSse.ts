// Parsing for Omi's /v2/messages SSE reply stream, shared by the renderer chat
// (useChat) and the main-process AI-clone reply engine so the two can't drift.
//
// Each SSE line arrives as `data: <chunk>` (with a raw `done:` line marking the
// end). The backend also (a) emits ephemeral "thinking" status events whose
// payload starts with `think:` ("Checking action items", "Searching memories")
// — those aren't part of the reply — and (b) encodes reply newlines as the
// literal token `__CRLF__` so they survive single-line SSE framing.

/** Parse one SSE line into reply content, or null if it isn't reply content. */
export function parseOmiSseLine(line: string): string | null {
  if (!line || line.startsWith('done:')) return null
  const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
  if (content.startsWith('think:')) return null
  return content.replace(/__CRLF__/g, '\n')
}

/**
 * Incremental accumulator over raw stream text: feed decoded chunks as they
 * arrive (chunks may split lines arbitrarily); `text` holds the reply so far.
 */
export class OmiSseAccumulator {
  private buffer = ''
  text = ''

  /** Feed one decoded chunk; returns the new reply content it contributed. */
  feed(chunk: string): string {
    this.buffer += chunk
    const lines = this.buffer.split('\n')
    this.buffer = lines.pop() ?? ''
    let added = ''
    for (const line of lines) {
      const content = parseOmiSseLine(line)
      if (content !== null) added += content
    }
    this.text += added
    return added
  }

  /** Flush any trailing unterminated line (call once at end of stream). */
  end(): string {
    const content = this.buffer ? parseOmiSseLine(this.buffer) : null
    this.buffer = ''
    if (content === null) return ''
    this.text += content
    return content
  }
}
