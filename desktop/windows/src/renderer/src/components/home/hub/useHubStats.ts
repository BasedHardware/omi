import { useEffect, useState } from 'react'
import { useMemories } from '../../../hooks/useMemories'
import { fetchAllActionItems } from '../../../lib/actionItems'
import { conversationsCache, subscribeConversationsCache } from '../../../lib/pageCache'
import type { ConversationRow } from '../../../lib/pageCache'
import type { HubStatCounts } from './HubStatRibbon'

// The stat ribbon's four counts. The app has no count-only API, so each number is
// sourced from the same place its destination page gets its data — never a second,
// divergent fetch.
//
// A count stays null until it is KNOWN, and null renders as an em-dash: a 0 is a
// claim about the user's data, and we don't make a claim we can't back.

// The Conversations page fetches exactly ONE cloud page (limit 100, no paging) and
// merges local + pending rows on top, so its cloud slice is a page, not a total — a
// user with 500 conversations has 100 cloud rows in that cache. Rendering it as
// "100" would be a page length wearing a total's clothes. So when the cloud page
// comes back FULL we only know the true count is AT LEAST this many, and the ribbon
// says so ("100+"); a short page IS the whole set and is rendered exactly.
const CLOUD_PAGE_SIZE = 100

export function useHubStats(): HubStatCounts {
  const { memories, loading: memoriesLoading, error: memoriesError } = useMemories()

  // Tasks: the SAME local-first read the Tasks page uses (incomplete + completed
  // rows from the store), so this is a true total, not a first page. Subscribe to
  // `onTasksChanged` so the count re-reads when a task is added/completed anywhere.
  const [tasks, setTasks] = useState<number | null>(null)
  useEffect(() => {
    let live = true
    const read = (): void => {
      fetchAllActionItems()
        .then((items) => {
          if (live) setTasks(items.length)
        })
        // Leave the cell unknown (em-dash) rather than assert a wrong number.
        .catch(() => {})
    }
    read()
    const unsub = window.omi?.onTasksChanged?.(read)
    return () => {
      live = false
      unsub?.()
    }
  }, [])

  // Screenshots: a real COUNT(*) over the rewind frames table. NOT useRewind() —
  // that loads full frame rows for a 24h window and re-polls every second, so its
  // length is neither a total nor cheap.
  const [screenshots, setScreenshots] = useState<number | null>(null)
  useEffect(() => {
    let live = true
    void window.omi
      ?.rewindFrameCount?.()
      .then((n) => {
        if (live) setScreenshots(n)
      })
      .catch(() => {})
    return () => {
      live = false
    }
  }, [])

  // Conversations: OBSERVE the Conversations page's cache instead of firing a second
  // identical request. That page is a kept-alive panel, so it hydrates and fills the
  // cache shortly after launch.
  const [rows, setRows] = useState<ConversationRow[] | null>(() => conversationsCache.rows)
  useEffect(() => subscribeConversationsCache(setRows), [])

  const cloudRows = rows?.filter((r) => r.source === 'cloud').length ?? 0

  return {
    conversations: rows ? rows.length : null,
    conversationsAtLeast: cloudRows >= CLOUD_PAGE_SIZE,
    tasks,
    // A FAILED fetch leaves useMemories with an empty list and loading:false (its
    // `finally` marks the cache loaded either way), so keying only on `loading`
    // would render "0 Memories" — a hard claim that the user has none — to anyone
    // who is merely offline. Unknown is an em-dash; 0 is a fact we only state when
    // we actually know it.
    memories: memoriesLoading || memoriesError ? null : memories.length,
    screenshots
  }
}
