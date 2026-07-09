// Generates the clone's reply by calling Omi's /v2/messages chat endpoint —
// the same memory-grounded pipeline as the in-app chat — with a persona
// wrapper so the answer reads as the user texting back, not an assistant.
// Main-process code: the renderer supplies the Firebase ID token.
import { OmiSseAccumulator } from '../../shared/omiSse'

export type ReplyTranscriptLine = { sender: string; text: string; fromMe: boolean }

export type ReplyContext = {
  /** How the user is addressed in the prompt ("Karthik"). */
  userDisplayName: string
  senderName: string
  chatTitle: string
  network: string
  /** Oldest→newest recent lines for tone/thread context. */
  transcript: ReplyTranscriptLine[]
  incomingText: string
}

export type ReplyResult =
  | { ok: true; text: string }
  | { ok: false; error: 'unauthorized' | 'http_error' | 'network' | 'empty'; detail?: string }

/** Decode the `done: <base64 json>` terminator's text field (service notices
 *  like plan limits arrive ONLY there, with no streamed chunks). */
export function decodeDoneNotice(raw: string): string | null {
  const m = raw.match(/(?:^|\n)done: (\S+)/)
  if (!m) return null
  try {
    const payload = JSON.parse(Buffer.from(m[1], 'base64').toString('utf8')) as { text?: string }
    return payload.text?.trim() || null
  } catch {
    return null
  }
}

export function buildPersonaPrompt(ctx: ReplyContext): string {
  const name = ctx.userDisplayName || 'the user'
  const lines = ctx.transcript
    .map((l) => `${l.fromMe ? name : l.sender}: ${l.text}`)
    .join('\n')
  return [
    `You are ${name}'s AI clone answering a personal chat message on their behalf.`,
    `A contact named ${ctx.senderName} just messaged ${name} on ${ctx.network} (chat: "${ctx.chatTitle}").`,
    '',
    'Rules:',
    `- Reply in first person AS ${name}. Never mention being an AI, a clone, or an assistant.`,
    '- Natural texting style: short, casual, matches the tone of the conversation. No greetings or sign-offs unless the thread calls for one.',
    `- Use what you know about ${name} (their memories, life, work, preferences) to answer personal questions accurately.`,
    "- If you genuinely don't know something personal, deflect casually — never invent facts.",
    '- Output ONLY the reply message text. No quotes, labels, or explanations.',
    '',
    ...(lines ? ['Recent conversation:', lines, ''] : []),
    `${ctx.senderName}'s new message: ${ctx.incomingText}`,
    '',
    `${name}'s reply:`
  ].join('\n')
}

export async function generateReply(args: {
  apiBase: string
  /** When set, quota-limited /v2/messages falls back to this chat-completions
   *  lane (separately rate-limited; not memory-grounded but keeps replies
   *  flowing) — the same fallback pairing agentLLM.ts uses, in reverse. */
  desktopApiBase?: string
  firebaseToken: string
  ctx: ReplyContext
  fetchImpl?: typeof fetch
}): Promise<ReplyResult> {
  const doFetch = args.fetchImpl ?? fetch
  const prompt = buildPersonaPrompt(args.ctx)
  let res: Response
  try {
    res = await doFetch(`${args.apiBase}/v2/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${args.firebaseToken}`
      },
      body: JSON.stringify({ text: prompt })
    })
  } catch (e) {
    return { ok: false, error: 'network', detail: (e as Error).message }
  }
  if (res.status === 401 || res.status === 403) return { ok: false, error: 'unauthorized' }
  if (!res.ok || !res.body) return { ok: false, error: 'http_error', detail: `HTTP ${res.status}` }

  const acc = new OmiSseAccumulator()
  let raw = ''
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })
    raw += chunk
    acc.feed(chunk)
  }
  acc.end()

  const text = cleanReply(acc.text)
  if (text) return { ok: true, text }

  // No streamed chunks — the done: payload is a service notice (e.g. "monthly
  // chat limit reached"), which must NEVER be sent to a contact. Fall back to
  // the desktop chat-completions lane; surface the notice if that fails too.
  const notice = decodeDoneNotice(raw)
  const fallback = args.desktopApiBase
    ? await completionsFallback(doFetch, args.desktopApiBase, args.firebaseToken, prompt)
    : null
  if (fallback) return { ok: true, text: fallback }
  return { ok: false, error: 'empty', detail: notice ?? undefined }
}

async function completionsFallback(
  doFetch: typeof fetch,
  desktopApiBase: string,
  firebaseToken: string,
  prompt: string
): Promise<string | null> {
  try {
    const res = await doFetch(`${desktopApiBase}/v2/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${firebaseToken}`
      },
      body: JSON.stringify({
        model: FALLBACK_MODEL,
        stream: false,
        messages: [
          {
            // Without this, the model prefixes meta-commentary ("I don't have
            // information about…") before the actual reply — which would land
            // in the contact's chat verbatim.
            role: 'system',
            content:
              'You draft chat replies on behalf of the user. Respond with ONLY the reply message text — no commentary, no reasoning, no explanations, no quotes around it. If you lack a personal detail, the reply itself should deflect casually instead of mentioning missing information.'
          },
          { role: 'user', content: prompt }
        ]
      })
    })
    if (!res.ok) return null
    const body = (await res.json()) as { choices?: { message?: { content?: string } }[] }
    return cleanReply(body.choices?.[0]?.message?.content ?? '') || null
  } catch {
    return null
  }
}

/** Same model the desktop action planner uses (agentLLM.ts). */
const FALLBACK_MODEL = 'claude-haiku-4-5-20251001'

/** Strip whitespace and any wrapping quotes the model added despite the rules. */
export function cleanReply(raw: string): string {
  let text = raw.trim()
  if (text.length > 1 && text.startsWith('"') && text.endsWith('"')) {
    text = text.slice(1, -1).trim()
  }
  return text
}
