import { useEffect, useMemo, useState } from 'react'
import { useMemories } from '../../../hooks/useMemories'
import { fetchAllActionItems } from '../../../lib/actionItems'
import { auth, onAuthStateChanged } from '../../../lib/firebase'
import { conversationsCache, subscribeConversationsCache } from '../../../lib/pageCache'
import type { ConversationRow } from '../../../lib/pageCache'
import type { HubStatCounts } from './HubStatRibbon'
import { getCachedHubStats, overlay, persistHubStats } from './hubStatsCache'

// The stat ribbon's four counts. The app has no count-only API, so each number is
// sourced from the same place its destination page gets its data — never a second,
// divergent fetch.
//
// A count stays null until it is KNOWN, and null renders as an em-dash: a 0 is a
// claim about the user's data, and we don't make a claim we can't back.
//
// COLD START: each source is an async fetch with no synchronous seed, so a fresh
// launch would show four em-dashes for the second or two until they resolve. To
// avoid that, the last-known counts are cached per-account (hubStatsCache) and
// rendered IMMEDIATELY; the live fetches then overwrite each cell as they land
// (stale-while-revalidate). The cache is uid-stamped, so a different account on
// the same machine never inherits the previous user's numbers.

// The Conversations page fetches exactly ONE cloud page (limit 100, no paging) and
// merges local + pending rows on top, so its cloud slice is a page, not a total — a
// user with 500 conversations has 100 cloud rows in that cache. Rendering it as
// "100" would be a page length wearing a total's clothes. So when the cloud page
// comes back FULL we only know the true count is AT LEAST this many, and the ribbon
// says so ("100+"); a short page IS the whole set and is rendered exactly.
const CLOUD_PAGE_SIZE = 100

export function useHubStats(): HubStatCounts {
  // The account the cache is scoped to. Read synchronously so the FIRST render
  // already resolves the right blob (no em-dash flash), and track auth changes so
  // an in-place account switch re-reads under the new uid (the cross-account
  // guard). This is a pure read-only subscription — no teardown/reconcile side
  // effects (that lives in useAuth); several listeners on `auth` are fine.
  const [uid, setUid] = useState<string | null>(() => auth.currentUser?.uid ?? null)
  useEffect(() => onAuthStateChanged(auth, (u) => setUid(u?.uid ?? null)), [])
  const cached = useMemo(() => getCachedHubStats(uid), [uid])

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

  // The freshly-fetched counts (null = still unknown this session), exactly as
  // before caching existed.
  const live: HubStatCounts = {
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

  // Persist each known cell so the NEXT cold launch starts from these (per-uid).
  useEffect(() => {
    persistHubStats(uid, live)
    // Depend on the primitive count fields, not the `live` object (rebuilt every
    // render) — the effect must fire only when a value actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    uid,
    live.conversations,
    live.conversationsAtLeast,
    live.tasks,
    live.memories,
    live.screenshots
  ])

  // Stale-while-revalidate: the cached values fill any cell the live fetch hasn't
  // resolved yet, so the ribbon shows numbers from the first paint.
  return overlay(cached, live)
}
