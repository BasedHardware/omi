import { auth } from './firebase'

export type GeminiPart = { text: string } | { inlineData: { mimeType: string; data: string } }

export type GenerateArgs = {
  model: string
  parts: GeminiPart[]
  systemPrompt?: string
  responseSchema?: Record<string, unknown>
  thinkingBudget?: number
}

const DEFAULT_MODEL = (import.meta.env.VITE_GEMINI_MODEL as string) || 'gemini-2.5-flash'
const MAX_RETRIES = 2

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/**
 * Generate text from Gemini via Omi's desktop-backend proxy. Mirrors the macOS
 * GeminiClient: Firebase Bearer auth (the backend injects the real Gemini key),
 * multimodal parts, optional structured output, retry on 429/503.
 */
export async function generate(args: GenerateArgs): Promise<string> {
  const model = args.model || DEFAULT_MODEL
  const base = import.meta.env.VITE_OMI_DESKTOP_API_BASE as string
  const url = `${base}/v1/proxy/gemini/models/${model}:generateContent`

  const body: Record<string, unknown> = {
    contents: [{ role: 'user', parts: args.parts }]
  }
  if (args.systemPrompt) {
    body.systemInstruction = { parts: [{ text: args.systemPrompt }] }
  }
  const genConfig: Record<string, unknown> = {}
  if (args.responseSchema) {
    genConfig.responseMimeType = 'application/json'
    genConfig.responseSchema = args.responseSchema
  }
  if (typeof args.thinkingBudget === 'number') {
    genConfig.thinkingConfig = { thinkingBudget: args.thinkingBudget }
  }
  if (Object.keys(genConfig).length) body.generationConfig = genConfig

  const token = (await auth.currentUser?.getIdToken()) ?? ''

  let lastError = ''
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body)
    })
    if (res.ok) {
      const json = (await res.json()) as {
        candidates?: { content?: { parts?: { text?: string }[] } }[]
      }
      const text = json.candidates?.[0]?.content?.parts?.map((p) => p.text ?? '').join('') ?? ''
      return text.trim()
    }
    if (res.status === 429 || res.status === 503) {
      lastError = `status ${res.status}`
      await sleep(400 * (attempt + 1))
      continue
    }
    // Non-retryable — surface a sanitized message (don't echo the proxy body,
    // which can include tokens/keys).
    throw new Error(`Gemini proxy request failed (status ${res.status})`)
  }
  throw new Error(`Gemini proxy request failed after retries (${lastError})`)
}
