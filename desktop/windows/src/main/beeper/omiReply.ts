// Isolated chat-reply generation through Omi /v2/messages so replies are
// memory-grounded (RAG) without writing into the user's main Chat tab.
// Isolated via app_id=omi-beeper-reply — unknown app ids are allowed and key a
// separate chat_db session (backend/routers/chat.py).
import { net } from 'electron'
import { fetchWithFreshToken, getAbortSignal, getSessionEpoch } from '../assistants/core/session'
import { recordFallback } from '../observability/fallback'

// Copy of renderer/src/lib/messagesSse.parseMessagesSse — main must not import
// renderer modules. Keep in lockstep with that helper.
function parseMessagesSse(raw: string): string {
  const out: string[] = []
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith('done:') || line.startsWith('message:')) continue
    const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
    if (content.startsWith('think:')) continue
    out.push(content)
  }
  return out.join('').replace(/__CRLF__/g, '\n')
}

const APP_ID = 'omi-beeper-reply'
const TIMEOUT_MS = 45_000

export async function generateChatReply(prompt: string): Promise<string> {
  const epoch = getSessionEpoch()
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  const onAbort = (): void => ctrl.abort()
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onAbort, { once: true })

  try {
    const res = await fetchWithFreshToken((session) => {
      if (getSessionEpoch() !== epoch) throw new Error('session changed')
      return net.fetch(`${session.apiBase}/v2/messages?app_id=${encodeURIComponent(APP_ID)}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.token}`,
          'Content-Type': 'application/json',
          'X-App-Platform': 'windows'
        },
        body: JSON.stringify({ text: prompt }),
        signal: ctrl.signal
      })
    }, 'beeper_reply')

    if (getSessionEpoch() !== epoch) throw new Error('session changed')
    if (!res.ok) {
      recordFallback({
        component: 'other',
        from: 'beeper_reply',
        to: 'none',
        reason: 'other',
        outcome: 'exhausted',
        status: res.status
      })
      throw new Error(`omi reply HTTP ${res.status}`)
    }
    const text = parseMessagesSse(await res.text())
    if (!text.trim()) throw new Error('empty omi reply')
    return text
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}
