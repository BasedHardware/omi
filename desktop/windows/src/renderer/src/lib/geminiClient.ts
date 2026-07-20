import { callAgentLLM } from './agentLLM'

export type GeminiPart = { text: string } | { inlineData: { mimeType: string; data: string } }

export type GenerateArgs = {
  model: string
  parts: GeminiPart[]
  systemPrompt?: string
  responseSchema?: Record<string, unknown>
  thinkingBudget?: number
}

export async function generate(args: GenerateArgs): Promise<string> {
  if (args.parts.some((part) => 'inlineData' in part)) {
    throw new Error('The Omi agent runtime does not support inline media prompts.')
  }
  if (typeof args.thinkingBudget === 'number') {
    throw new Error('The Omi agent runtime does not support a thinking budget.')
  }
  const schema = args.responseSchema ? `\n\nRespond only with JSON matching this schema:\n${JSON.stringify(args.responseSchema)}` : ''
  const text = args.parts.map((part) => ('text' in part ? part.text : '')).join('\n')
  return callAgentLLM(`${args.systemPrompt ? `${args.systemPrompt}\n\n` : ''}${text}${schema}`)
}
