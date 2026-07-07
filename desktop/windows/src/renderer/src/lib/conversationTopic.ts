import { desktopApi } from './apiClient'
import { extractJSONObject } from './extractJson'

const MODEL = 'claude-haiku-4-5-20251001'

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
  try {
    const res = await desktopApi.post('/v2/chat/completions', {
      model: MODEL,
      stream: false,
      messages: [
        {
          role: 'user',
          content:
            'Summarize this conversation as a topic. Respond with ONLY a JSON object ' +
            '{"emoji":"<one emoji that captures the topic>","title":"<a short title, max 5 words>"} ' +
            'and nothing else.\n\nTranscript:\n' +
            text.slice(0, 4000)
        }
      ]
    })
    const content =
      (res.data as { choices?: { message?: { content?: string } }[] })?.choices?.[0]?.message
        ?.content ?? ''
    const obj = JSON.parse(extractJSONObject(content)) as { emoji?: unknown; title?: unknown }
    const emoji = typeof obj.emoji === 'string' ? obj.emoji.trim() : ''
    const title = typeof obj.title === 'string' ? obj.title.trim() : ''
    if (!emoji && !title) return null
    return { emoji, title }
  } catch {
    return null
  }
}
