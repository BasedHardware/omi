import { useEffect, useState } from 'react'
import { listChatApps, type ChatApp } from '../lib/chatApps'

// Fetches the user's enabled chat-capable apps once on mount, for the chat-app /
// persona picker (Mac ChatProvider.chatApps). `list` is injectable so the picker
// can be unit-tested without the axios/Firebase module graph. Kept in its own file
// (not the component) so the picker file only exports components — react-refresh.
export function useChatApps(list: () => Promise<ChatApp[]> = listChatApps): {
  chatApps: ChatApp[]
  loading: boolean
} {
  const [chatApps, setChatApps] = useState<ChatApp[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    void list()
      .then((apps) => {
        if (!cancelled) setChatApps(apps)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [list])
  return { chatApps, loading }
}
