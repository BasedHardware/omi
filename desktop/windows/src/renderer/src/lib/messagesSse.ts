// Reconstruct the assistant reply from Omi's /v2/messages SSE response when it's
// consumed as one buffered string (not streamed). Mirrors useChat's streaming
// parse: each line is `data: <chunk>` (drop the prefix), `done:` marks the end,
// `think:` payloads are ephemeral status events (drop them), and reply newlines
// are encoded as the literal token __CRLF__. Pure — no imports — so it's unit
// testable without dragging in firebase/apiClient.
export function parseMessagesSse(raw: string): string {
  const out: string[] = []
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith('done:')) continue
    const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
    if (content.startsWith('think:')) continue
    out.push(content)
  }
  return out.join('').replace(/__CRLF__/g, '\n')
}
