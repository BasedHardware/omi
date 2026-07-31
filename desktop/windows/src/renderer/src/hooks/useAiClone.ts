// Track 2 (AI clone) — Settings → AI Clone's data layer. Mirrors
// useCodingAgents.ts's shape (fetch on mount, expose a refresh()) since the
// two settings tabs have the same "connection + list + refresh" structure.
import { useCallback, useEffect, useState } from 'react'
import type { AiCloneChatSummary, AiCloneStatus, AiClonePendingDraft } from '../../../shared/types'

export function useAiCloneStatus(): { status: AiCloneStatus; refresh: () => void } {
  const [status, setStatus] = useState<AiCloneStatus>({ connected: false, accounts: [] })
  const refresh = useCallback((): void => {
    void window.omi
      .aiCloneStatus()
      .then(setStatus)
      .catch(() => setStatus({ connected: false, accounts: [] }))
  }, [])
  useEffect(refresh, [refresh])
  return { status, refresh }
}

export function useAiCloneChats(): {
  chats: AiCloneChatSummary[]
  refresh: () => void
} {
  const [chats, setChats] = useState<AiCloneChatSummary[]>([])
  // No need to branch on "connected" here — aiCloneListChats() resolves to []
  // whenever nothing's connected (main's clientOrNull() short-circuits), same
  // always-fetch shape as useCodingAgents.
  const refresh = useCallback((): void => {
    void window.omi
      .aiCloneListChats()
      .then(setChats)
      .catch(() => setChats([]))
  }, [])
  useEffect(refresh, [refresh])
  return { chats, refresh }
}

export function useAiCloneDrafts(): { drafts: AiClonePendingDraft[]; refresh: () => void } {
  const [drafts, setDrafts] = useState<AiClonePendingDraft[]>([])
  const refresh = useCallback((): void => {
    void window.omi
      .aiCloneListDrafts()
      .then(setDrafts)
      .catch(() => setDrafts([]))
  }, [])
  useEffect(refresh, [refresh])
  return { drafts, refresh }
}
