import { useCallback, useEffect, useState } from 'react'
import { GOOGLE_ENABLED } from '../lib/googleFeatureFlag'
import { runGoogleSync } from '../lib/googleSync'
import { toast } from '../lib/toast'
import { useMemories } from './useMemories'
import type { GoogleStatus } from '../../../shared/types'

// The CLIENT-SIDE Gmail lane (loopback OAuth) shared by Settings → Integrations and
// the Hub → Connections Email card, so the gate, status, connect/disconnect/sync,
// and the background auto-resync live in exactly ONE place. Previously each surface
// inlined its own copy — and the Hub card was missing the auto-resync entirely.
export { GOOGLE_ENABLED }

// --- Singleton auto-sync scheduler -----------------------------------------
// sync-on-connect + a 15-minute polling resync while connected, owned at module
// scope so it fires exactly ONCE no matter how many mounts (Settings + Hub) hold
// the hook — never one interval per mount, never a double sync-on-connect.
let autoSyncTimer: ReturnType<typeof setInterval> | null = null
let autoSyncRunning = false

// Fed by whichever hook is mounted; every mount points at the same useMemories
// cache, so last-writer-wins is equivalent. The background resync reads these so it
// dedups against current memories and refreshes the Memories page after a write.
let readExistingMemories: () => string[] = () => []
let refreshMemories: () => Promise<void> = async () => {}

// Shared status, broadcast to every mount (mirrors useMemories) so connecting in
// one surface immediately reflects in the other.
const statusSubscribers = new Set<(s: GoogleStatus) => void>()
let sharedStatus: GoogleStatus = { connected: false }
let statusLoaded = false

function publishStatus(s: GoogleStatus): void {
  sharedStatus = s
  statusSubscribers.forEach((fn) => fn(s))
}

async function runAutoSync(): Promise<void> {
  // Guard overlap: a slow sync must not stack with the next tick.
  if (autoSyncRunning) return
  autoSyncRunning = true
  try {
    const out = await runGoogleSync(readExistingMemories())
    if (out.memoriesAdded > 0) await refreshMemories()
    publishStatus(await window.omi.googleStatus())
  } catch {
    // Background resync — swallow; the next tick or a manual Sync now retries.
  } finally {
    autoSyncRunning = false
  }
}

function ensureAutoSync(): void {
  if (autoSyncTimer !== null) return // singleton: one timer + one on-connect run
  void runAutoSync()
  autoSyncTimer = setInterval(() => void runAutoSync(), 15 * 60 * 1000)
}

function stopAutoSync(): void {
  if (autoSyncTimer === null) return
  clearInterval(autoSyncTimer)
  autoSyncTimer = null
}

export function useGoogleConnection(): {
  googleEnabled: boolean
  status: GoogleStatus
  connect: () => Promise<void>
  disconnect: () => Promise<void>
  syncNow: () => Promise<void>
  busy: boolean
  syncing: boolean
} {
  const { memories, refresh } = useMemories()
  const [status, setStatus] = useState<GoogleStatus>(sharedStatus)
  const [busy, setBusy] = useState(false)
  const [syncing, setSyncing] = useState(false)

  // Keep the singleton's memory providers fresh for the background resync.
  useEffect(() => {
    readExistingMemories = () => memories.map((m) => m.content)
    refreshMemories = refresh
  }, [memories, refresh])

  // Subscribe to the shared status so a connect/disconnect anywhere lands here.
  useEffect(() => {
    statusSubscribers.add(setStatus)
    return () => {
      statusSubscribers.delete(setStatus)
    }
  }, [])

  // Load status once per module lifetime; later mounts adopt the shared value
  // through useState's initializer (sharedStatus) + the subscription above, so
  // there's nothing to set here on a warm mount.
  useEffect(() => {
    if (!GOOGLE_ENABLED || statusLoaded) return
    statusLoaded = true
    window.omi
      .googleStatus()
      .then(publishStatus)
      .catch(() => {})
  }, [])

  // Drive the singleton off connected-ness. Intentionally NOT cleaned up on
  // unmount — the resync must keep running in the background while connected even
  // when neither surface is on screen (the bug the Hub card had).
  useEffect(() => {
    if (!GOOGLE_ENABLED) return
    if (status.connected) ensureAutoSync()
    else stopAutoSync()
  }, [status.connected])

  const connect = useCallback(async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      const next = await window.omi.googleConnect()
      // sync-on-connect is handled by the singleton (connected effect), so we don't
      // kick a sync here — that's what kept the two surfaces from double-syncing.
      publishStatus(next)
      if (next.connected) toast('Google connected', { tone: 'success', body: next.email })
    } catch (e) {
      toast('Could not connect Google', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }, [busy])

  const disconnect = useCallback(async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      publishStatus(await window.omi.googleDisconnect())
      toast('Google disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }, [busy])

  const syncNow = useCallback(async (): Promise<void> => {
    if (syncing) return
    setSyncing(true)
    try {
      const out = await runGoogleSync(memories.map((m) => m.content))
      if (out.errors.length > 0) {
        toast('Sync finished with errors', { tone: 'warn', body: out.errors.join('; ') })
      } else {
        toast(
          `Synced — ${out.memoriesAdded} memor${out.memoriesAdded === 1 ? 'y' : 'ies'}, ${out.tasksAdded} task${out.tasksAdded === 1 ? '' : 's'}`,
          { tone: 'success' }
        )
      }
      if (out.memoriesAdded > 0) await refresh()
      publishStatus(await window.omi.googleStatus())
    } catch (e) {
      toast('Google sync failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setSyncing(false)
    }
  }, [syncing, memories, refresh])

  return { googleEnabled: GOOGLE_ENABLED, status, connect, disconnect, syncNow, busy, syncing }
}
