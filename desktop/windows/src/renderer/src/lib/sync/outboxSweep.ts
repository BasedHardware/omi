// App-lifetime background retry for the conversation sync outbox. Before this,
// unsynced rows were only retried when the Conversations page mounted
// (retryUnsyncedConversations there), so a PTT-only user who never opens that
// page had their failed from-segments sync wedged for the whole session. macOS
// runs an unconditional 60s retry timer from launch; this is the Windows port.
//
// Start on sign-in / launch, stop on sign-out. The pass itself is idempotent and
// shares retryUnsyncedConversations' 60s throttle with the page-mount trigger, so
// running both can't double-post.
import { retryUnsyncedConversations } from './conversationSync'

const SWEEP_INTERVAL_MS = 60_000

let timer: ReturnType<typeof setInterval> | null = null

async function sweepOnce(): Promise<void> {
  try {
    const locals = await window.omi.listLocalConversations()
    await retryUnsyncedConversations(locals)
  } catch (e) {
    console.warn('[outbox-sweep] pass failed:', (e as Error).message)
  }
}

/** Begin the background sweep (idempotent). Fires one pass immediately so a
 *  PTT-only user's pending sync gets a shot at launch, then every 60s. */
export function startOutboxSweep(): void {
  if (timer) return
  void sweepOnce()
  timer = setInterval(() => void sweepOnce(), SWEEP_INTERVAL_MS)
}

/** Stop the background sweep (idempotent). Called on sign-out. */
export function stopOutboxSweep(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
