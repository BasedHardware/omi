import { omiApi } from './apiClient'

/**
 * Generate a topic emoji + short title for a finalized conversation from its
 * transcript — fast titling so a just-saved conversation doesn't sit "loading"
 * while the backend slowly processes it. The prompt and the model live in the
 * backend behind POST /v1/conversations/topic (managed conv_structure → Luna
 * SSOT). Best-effort: returns null on any failure (no title is a fine outcome —
 * the backend's title will arrive later).
 */
export async function generateConversationTopic(
  transcript: string,
  conversationLanguage?: string
): Promise<{ emoji: string; title: string } | null> {
  const text = transcript.trim()
  if (!text) return null
  try {
    const body: { transcript: string; conversation_language?: string } = { transcript: text.slice(0, 4000) }
    if (conversationLanguage) body.conversation_language = conversationLanguage
    const res = await omiApi.post('/v1/conversations/topic', body)
    const data = res.data as { emoji?: unknown; title?: unknown }
    const emoji = typeof data.emoji === 'string' ? data.emoji.trim() : ''
    const title = typeof data.title === 'string' ? data.title.trim() : ''
    if (!emoji && !title) return null
    return { emoji, title }
  } catch {
    return null
  }
}
