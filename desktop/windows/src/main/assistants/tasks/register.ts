// Bring the Task assistant up: register it with the coordinator (which starts the
// shared analysis loop if the master toggle is on) and expose the dev-only IPCs.
// Mirrors memory/register.ts. There is no prompt migration to run — Mac's task
// prompt has no version constant.
//
// Also owns the one-time embedding-index bring-up (loadIndex + backfillMissing).
// Those were shipped by PR-A but never wired anywhere; PR-B is where the index is
// first loaded and any pre-existing task titles are swept into it.
import { ipcMain } from 'electron'
import { is } from '@electron-toolkit/utils'
import { registerAssistant } from '../core/coordinator'
import { latestRewindFrame } from '../../ipc/db'
import { getAppSettings } from '../../appSettings'
import { getBackendSession } from '../core/session'
import { backfillMissing, loadIndex } from '../../tasks/taskEmbeddingService'
import { getTaskAssistant } from './taskAssistant'

let registered = false

export function registerTaskAssistant(): void {
  if (registered) return
  registered = true

  registerAssistant(getTaskAssistant())

  if (is.dev) {
    // Force one real extraction of the latest captured frame, so the pipeline can
    // be exercised without waiting for the interval / a context switch. Non-prod
    // only — never expose an on-demand cloud vision call in a shipped build.
    ipcMain.handle('tasks:analyzeNow', async () => {
      const frame = latestRewindFrame()
      if (!frame) return { ok: false, reason: 'no-frame' }
      await getTaskAssistant().analyzeNowForDev(frame)
      return { ok: true }
    })

    // Observability for the gate: the REAL isEnabled() (decided solely by
    // taskEnabled) alongside the coordinator's master screen-analysis lever.
    ipcMain.handle('tasks:debugIsEnabled', async () => {
      const settings = getAppSettings()
      return {
        isEnabled: getTaskAssistant().isEnabled(),
        taskEnabled: settings.taskEnabled,
        screenAnalysisEnabled: settings.screenAnalysisEnabled
      }
    })
  }
}

// Poll cadence + cap for the backfill's session wait — the renderer relays a
// Firebase session a few seconds after startup, so a backfill kicked at app-ready
// would find none and give up for the whole launch. Poll briefly, run once, stop.
const SESSION_POLL_MS = 5_000
const SESSION_POLL_MAX_ATTEMPTS = 60 // ~5 min

/**
 * Bring the task-title embedding index up on startup (loadIndex + a one-shot
 * backfillMissing). `loadIndex` is a pure local read, safe and idempotent
 * regardless of session. `backfillMissing` needs a signed-in session (it embeds
 * via the backend proxy), so we poll until one exists, run the sweep once, and
 * stop. Never throws at startup — both calls are best-effort.
 */
export function bringUpTaskEmbeddingIndex(): void {
  try {
    loadIndex()
  } catch (e) {
    console.warn('[tasks] embedding index load failed:', e instanceof Error ? e.name : 'Error')
  }

  // If a session is already present, sweep immediately; otherwise poll for one.
  if (getBackendSession()) {
    void runBackfillOnce()
    return
  }
  let attempts = 0
  const timer = setInterval(() => {
    attempts += 1
    if (getBackendSession()) {
      clearInterval(timer)
      void runBackfillOnce()
    } else if (attempts >= SESSION_POLL_MAX_ATTEMPTS) {
      clearInterval(timer) // never signed in this launch — the next launch retries
    }
  }, SESSION_POLL_MS)
  timer.unref?.()
}

function runBackfillOnce(): Promise<void> {
  return backfillMissing().catch((e) => {
    console.warn('[tasks] embedding backfill failed:', e instanceof Error ? e.name : 'Error')
  })
}
