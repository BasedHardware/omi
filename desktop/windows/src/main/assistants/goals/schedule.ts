// The periodic trigger + gates for client-side goal generation, plus the manual
// `generateGoalNow()` the Suggest button calls. Windows main has no
// conversation-created signal (Mac's per-conversation hook), so the AUTO path is
// a time-driven job: check on app-ready (once a session exists) and every few
// hours after, gated by [toggle ON] + [<3 active goals] + [a new calendar day
// since the last generation]. Stale cleanup runs first so aged auto-goals can't
// clog the `<3` gate forever.
//
// The MANUAL path bypasses the day + count gates (the user explicitly asked) but
// still requires a signed-in session and sufficient context; it retries a
// transport failure up to 3× with a 5s backoff (Mac's generateNow cadence).
import { getAppSettings, setAppSettings } from '../../appSettings'
import { getBackendSession } from '../core/session'
import { fetchGoalContext } from './context'
import {
  realGenerateDeps,
  runGoalGenerationWith,
  type GenerateDeps,
  type GenerateResult
} from './generate'
import { removeStaleGoals } from './staleCleanup'

/** Mac's `maxActiveGoals` — auto-gen pauses at 3 active goals. */
const MAX_ACTIVE_GOALS = 3
/** Re-check every 4h (Windows has no conversation hook — this is the heartbeat).
 *  The calendar-day gate keeps actual generation to ≤1/day regardless. */
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000
/** Startup session wait (the renderer relays a session a few seconds post-launch);
 *  mirrors tasks/register.bringUpTaskEmbeddingIndex. */
const SESSION_POLL_MS = 5_000
const SESSION_POLL_MAX_ATTEMPTS = 60 // ~5 min
/** Manual prereq wait: poll for a session up to ~10s before giving up. */
const MANUAL_SESSION_WAIT_MS = 10_000
const MANUAL_SESSION_POLL_MS = 500
/** Manual retry: 3 attempts, 5s between (Mac's generateNow backoff). */
const MANUAL_MAX_ATTEMPTS = 3
const MANUAL_BACKOFF_MS = 5_000

let isGenerating = false
let timer: ReturnType<typeof setInterval> | null = null

/** Local calendar date `YYYY-MM-DD` for the once-per-day gate. Local (not UTC) so
 *  "a new day" matches the user's wall clock. */
export function localDateString(d: Date = new Date()): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms)
    t.unref?.()
  })
}

/** Mark today as generated so neither the auto timer nor a later manual run fires
 *  a second goal the same calendar day. */
function markGeneratedToday(): void {
  setAppSettings({ goalGenerationLastDate: localDateString() })
}

/**
 * The auto path, run on the timer + at startup. Fire-and-forget: never throws.
 * Gates in order — cheap ones first, then the heavy context fetch:
 *   toggle ON → session present → not already generated today → cleanup stale →
 *   <3 active → sufficient context → generate → stamp the day.
 * The context is fetched ONCE and injected into generation (no double fetch).
 */
export async function runGoalGenerationIfDue(): Promise<void> {
  const settings = getAppSettings()
  if (!settings.goalAutoGenerationEnabled) return
  if (!getBackendSession()) return // defer to the next tick / next session
  if (isGenerating) return
  if (settings.goalGenerationLastDate === localDateString()) return // already today

  isGenerating = true
  try {
    // Unclog first: without this, 3 aged auto-goals wedge the <3 gate permanently.
    await removeStaleGoals().catch((e) =>
      console.warn('[goals] cleanup failed:', e instanceof Error ? e.name : 'Error')
    )

    const context = await fetchGoalContext()
    if (!context) return // session vanished mid-run
    if (context.activeGoalCount >= MAX_ACTIVE_GOALS) return

    // Reuse the fetched context (skip generate.ts's own fetch) via an override.
    const deps: GenerateDeps = {
      ...realGenerateDeps({ manual: false }),
      getContext: async () => context
    }
    const result = await runGoalGenerationWith(deps)
    if (result.status === 'created') markGeneratedToday()
  } catch (e) {
    console.warn('[goals] auto generation failed:', e instanceof Error ? e.name : 'Error')
  } finally {
    isGenerating = false
  }
}

/**
 * The manual path (Suggest button IPC). Bypasses the day + count gates — the user
 * asked directly — but waits briefly for a session and retries a transport failure
 * 3× / 5s. Returns the outcome for the renderer to toast. On a created goal it
 * also stamps the day so the auto timer won't add a second one today.
 */
export async function generateGoalNow(): Promise<GenerateResult> {
  // Prereq wait: a signed-in session within ~10s, else give up cleanly.
  const deadline = Date.now() + MANUAL_SESSION_WAIT_MS
  while (!getBackendSession() && Date.now() < deadline) await sleep(MANUAL_SESSION_POLL_MS)
  if (!getBackendSession()) return { status: 'skipped', reason: 'no_session' }

  if (isGenerating) return { status: 'skipped', reason: 'error' } // an auto run holds the lock
  isGenerating = true
  try {
    let lastError: unknown
    for (let attempt = 0; attempt < MANUAL_MAX_ATTEMPTS; attempt++) {
      try {
        const result = await runGoalGenerationWith(realGenerateDeps({ manual: true }))
        // A skip (insufficient context / invalid model output) won't change in 5s —
        // return it rather than burn retries. Only transport throws are retried.
        if (result.status === 'created') markGeneratedToday()
        return result
      } catch (e) {
        lastError = e
        if (attempt < MANUAL_MAX_ATTEMPTS - 1) await sleep(MANUAL_BACKOFF_MS)
      }
    }
    console.warn(
      '[goals] manual generation failed after retries:',
      lastError instanceof Error ? lastError.name : 'Error'
    )
    return { status: 'skipped', reason: 'error' }
  } finally {
    isGenerating = false
  }
}

/**
 * Bring the goal scheduler up at startup: poll briefly for a session, run one due
 * check, and arm the recurring 4h timer. Idempotent. Never throws — a due check
 * that fails is logged and the timer keeps ticking.
 */
export function startGoalScheduler(): void {
  const kick = (): void => {
    void runGoalGenerationIfDue()
  }

  if (getBackendSession()) kick()
  else {
    let attempts = 0
    const poll = setInterval(() => {
      attempts += 1
      if (getBackendSession()) {
        clearInterval(poll)
        kick()
      } else if (attempts >= SESSION_POLL_MAX_ATTEMPTS) {
        clearInterval(poll) // never signed in this launch — the timer still retries
      }
    }, SESSION_POLL_MS)
    poll.unref?.()
  }

  if (!timer) {
    timer = setInterval(kick, CHECK_INTERVAL_MS)
    timer.unref?.()
  }
}

/** Test/teardown: stop the recurring timer. */
export function stopGoalScheduler(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
