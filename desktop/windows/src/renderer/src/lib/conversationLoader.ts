import { omiApi } from './apiClient'
import { native } from './native'
import {
  conversationsCache,
  getPendingConversations,
  reconcilePending,
  type ConversationRow
} from './pageCache'
import type { LocalConversation } from '../../../shared/types'
import type { Conversation as CloudConversation } from './omiApi.generated'

let loadingConversations: Promise<ConversationRow[]> | null = null

function summarize(segments: { text: string }[] | undefined): string {
  if (!segments || segments.length === 0) return ''
  return segments
    .map((segment) => segment.text)
    .filter(Boolean)
    .join(' ')
}

export function localToRow(conversation: LocalConversation): ConversationRow {
  const isChat = conversation.kind === 'chat'
  const rawPreview = isChat
    ? (conversation.messages?.find((message) => message.role === 'user')?.content ?? '')
    : conversation.transcript
  const preview = rawPreview
    ? rawPreview.slice(0, 200) + (rawPreview.length > 200 ? '…' : '')
    : isChat
      ? '(empty chat)'
      : '(empty transcript)'
  return {
    id: conversation.id,
    title: conversation.title || (isChat ? 'Chat with Omi' : 'Local recording'),
    subtitle: isChat
      ? `${new Date(conversation.startedAt).toLocaleString()} · ${conversation.messages?.length ?? 0} messages`
      : `${new Date(conversation.startedAt).toLocaleString()} · ${Math.round(
          (conversation.endedAt - conversation.startedAt) / 1000
        )}s`,
    preview,
    source: 'local',
    localKind: isChat ? 'chat' : 'recording',
    sortAt: conversation.createdAt
  }
}

export async function loadConversations(force = false): Promise<ConversationRow[]> {
  if (!force && conversationsCache.loaded && conversationsCache.rows) return conversationsCache.rows
  if (loadingConversations) return loadingConversations
  loadingConversations = (async () => {
    conversationsCache.error = null
    const rows: ConversationRow[] = []
    try {
      const response = await omiApi.get<CloudConversation[]>('/v1/conversations', {
        params: { limit: 100, offset: 0 }
      })
      for (const conversation of Array.isArray(response.data) ? response.data : []) {
        const created = conversation.created_at ? new Date(conversation.created_at).getTime() : 0
        rows.push({
          id: conversation.id,
          title: conversation.structured?.title || 'Untitled conversation',
          emoji: conversation.structured?.emoji || undefined,
          subtitle: conversation.created_at
            ? new Date(conversation.created_at).toLocaleString()
            : '',
          preview:
            conversation.structured?.overview ||
            summarize(conversation.transcript_segments).slice(0, 200) ||
            '(no transcript)',
          source: 'cloud',
          sortAt: created
        })
      }
    } catch (error) {
      conversationsCache.error = (error as Error).message
    }
    try {
      rows.push(...(await native.listLocalConversations()).map(localToRow))
    } catch (error) {
      console.error('Failed to load local conversations:', error)
    }
    reconcilePending(rows.filter((row) => row.source === 'cloud'))
    const merged = [...getPendingConversations(), ...rows].sort((a, b) => b.sortAt - a.sortAt)
    conversationsCache.rows = merged
    conversationsCache.loaded = true
    return merged
  })()
  try {
    return await loadingConversations
  } finally {
    loadingConversations = null
  }
}
