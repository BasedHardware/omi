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
  firebaseToken: string
  ctx: ReplyContext
  fetchImpl?: typeof fetch
}): Promise<ReplyResult> {
  const doFetch = args.fetchImpl ?? fetch
  let res: Response
  try {
    res = await doFetch(`${args.apiBase}/v2/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${args.firebaseToken}`
      },
      body: JSON.stringify({ text: buildPersonaPrompt(args.ctx) })
    })
  } catch (e) {
    return { ok: false, error: 'network', detail: (e as Error).message }
  }
  if (res.status === 401 || res.status === 403) return { ok: false, error: 'unauthorized' }
  if (!res.ok || !res.body) return { ok: false, error: 'http_error', detail: `HTTP ${res.status}` }

  const acc = new OmiSseAccumulator()
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    acc.feed(decoder.decode(value, { stream: true }))
  }
  acc.end()

  const text = cleanReply(acc.text)
  return text ? { ok: true, text } : { ok: false, error: 'empty' }
}

/** Strip whitespace and any wrapping quotes the model added despite the rules. */
export function cleanReply(raw: string): string {
  let text = raw.trim()
  if (text.length > 1 && text.startsWith('"') && text.endsWith('"')) {
    text = text.slice(1, -1).trim()
  }
  return text
}
