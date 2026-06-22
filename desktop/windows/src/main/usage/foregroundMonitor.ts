import { getForegroundExePath, subscribeForegroundChange } from './nativeForeground'
import { UsageAccumulator } from './usageAccumulator'
import { addAppUsage, pruneAppUsage } from '../ipc/db'
import { getUsageSettings } from './usageSettings'
import { usageCutoff } from './usageRetention'

// Switch boundaries are now captured precisely by the WinEvent hook, so the poll
// only needs to bank elapsed time for a long-running single app and cap idle
// gaps — it can be much coarser than before, cutting idle wakeups (closer to
// macOS's event-driven WindowMonitor).
const POLL_MS = 15_000
const FLUSH_MS = 60_000
// Cap a single attributed gap at 3 poll intervals so a stalled timer, sleep, or
// lock doesn't dump minutes onto whatever app happened to be foreground.
const MAX_GAP_MS = POLL_MS * 3

let pollTimer: NodeJS.Timeout | null = null
let flushTimer: NodeJS.Timeout | null = null
let unsubscribeForeground: (() => void) | null = null
let accumulator: UsageAccumulator | null = null

function flush(): void {
  if (!accumulator) return
  const now = Date.now()
  for (const { exePath, ms } of accumulator.drain()) {
    try {
      addAppUsage(exePath, ms / 1000, now)
    } catch (e) {
      console.warn('[usage] flush failed for', exePath, e)
    }
  }
}

// Start polling the foreground window. No-op when disabled by setting or when
// already running. Safe to call at app startup.
// Drop app_usage rows older than the user's configured retention window. Safe to
// call any time (startup, or right after the window is changed in Settings).
export function pruneUsageNow(): void {
  try {
    pruneAppUsage(usageCutoff(Date.now(), getUsageSettings().retentionDays))
  } catch (e) {
    console.warn('[usage] prune failed:', e)
  }
}

export function startForegroundMonitor(): void {
  if (pollTimer) return
  if (!getUsageSettings().enabled) return
  if (process.platform !== 'win32') return
  // Bound the table: drop apps not foregrounded within the retention window.
  pruneUsageNow()
  accumulator = new UsageAccumulator(MAX_GAP_MS)
  const sample = (): void => {
    try {
      accumulator?.addSample(getForegroundExePath(), Date.now())
    } catch (e) {
      console.warn('[usage] sample failed:', e)
    }
  }
  // Event-driven: credit the outgoing app the instant the foreground changes, so
  // switch boundaries are precise regardless of poll cadence.
  unsubscribeForeground = subscribeForegroundChange(sample)
  // Coarse poll: bank elapsed time for the current app and cap idle gaps.
  pollTimer = setInterval(sample, POLL_MS)
  flushTimer = setInterval(flush, FLUSH_MS)
  console.log('[usage] foreground monitor started')
}

// Force the in-memory accumulator to persist immediately, instead of waiting for
// the next FLUSH_MS tick. Used by the usage:flush IPC so the running tally is
// visible right away (the periodic flush only writes every 60s). No-op when the
// monitor isn't running.
export function flushForegroundMonitor(): void {
  flush()
}

export function stopForegroundMonitor(): void {
  if (pollTimer) clearInterval(pollTimer)
  if (flushTimer) clearInterval(flushTimer)
  if (unsubscribeForeground) unsubscribeForeground()
  pollTimer = null
  flushTimer = null
  unsubscribeForeground = null
  flush() // persist whatever was pending
  accumulator = null
  console.log('[usage] foreground monitor stopped')
}
