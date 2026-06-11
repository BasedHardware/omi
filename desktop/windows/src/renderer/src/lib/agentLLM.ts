import axios from 'axios'
import { desktopApi, omiApi } from './apiClient'
import { parseMessagesSse } from './messagesSse'

// Non-streaming single-shot completion used by the action planner & intent gate.
// Mirrors the model + endpoint localAgent.ts uses for its agent loop.
const AGENT_MODEL = 'claude-haiku-4-5-20251001'
const CALL_TIMEOUT_MS = 8000
const FALLBACK_TIMEOUT_MS = 30000

type ChatCompletion = { choices?: { message?: { content?: string } }[] }

// Fallback path: the conversational /v2/messages endpoint (api.omi.me), governed
// by a SEPARATE rate limit from the desktop agent endpoint. It streams SSE; we
// buffer the whole response (axios) and reconstruct the reply text. It's chat-
// tuned, but parseAutomationPlan tolerates surrounding prose, so a plan embedded
// in the reply still parses.
async function callViaMessages(prompt: string): Promise<string> {
  const res = await omiApi.post(
    '/v2/messages',
    { text: prompt },
    { responseType: 'text', timeout: FALLBACK_TIMEOUT_MS }
  )
  return parseMessagesSse(String(res.data ?? ''))
}

export async function callAgentLLM(prompt: string): Promise<string> {
  try {
    const res = await desktopApi.post(
      '/v2/chat/completions',
      { model: AGENT_MODEL, stream: false, messages: [{ role: 'user', content: prompt }] },
      { timeout: CALL_TIMEOUT_MS }
    )
    return (res.data as ChatCompletion)?.choices?.[0]?.message?.content ?? ''
  } catch (e) {
    // The desktop /v2/chat/completions endpoint is rate-limited per-account
    // independently of chat; when it 429s (or the transport fails outright),
    // fall back to /v2/messages so the planner still works. Other explicit
    // errors (e.g. 401 auth) propagate unchanged.
    const status = axios.isAxiosError(e) ? e.response?.status : undefined
    if (status === 429 || (axios.isAxiosError(e) && !e.response)) {
      return callViaMessages(prompt)
    }
    throw e
  }
}
