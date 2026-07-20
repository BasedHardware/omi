import { callAgentLLM } from './agentLLM'
import { extractJSONObject } from './extractJson'

/**
 * Generate a topic emoji + short title for a finalized conversation from its
 * transcript — fast client-side titling so a just-saved conversation doesn't sit
 * "loading" while the backend slowly processes it. Uses the same desktop
 * `/v2/chat/completions` path as kgSynthesis. Best-effort: returns null on any
 * failure (no title is a fine outcome — the backend's title will arrive later).
 */
export async function generateConversationTopic(
  transcript: string
): Promise<{ emoji: string; title: string } | null> {
  const text = transcript.trim()
  if (!text) return null
  const content = await callAgentLLM(
    'Summarize this conversation as a topic. Respond with ONLY a JSON object ' +
      '{"emoji":"<one emoji that captures the topic>","title":"<a short title, max 5 words>"} ' +
      'and nothing else.\n\nTranscript:\n' +
      text.slice(0, 4000)
  )
  const obj = JSON.parse(extractJSONObject(content)) as { emoji?: unknown; title?: unknown }
  const emoji = typeof obj.emoji === 'string' ? obj.emoji.trim() : ''
  const title = typeof obj.title === 'string' ? obj.title.trim() : ''
  if (!emoji && !title) throw new Error('Omi could not generate a conversation topic.')
  return { emoji, title }
}
