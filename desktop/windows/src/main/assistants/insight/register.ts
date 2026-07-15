// Bring the Insight assistant up: migrate its prompt version, register it with
// the coordinator (which starts the shared analysis loop if the master toggle is
// on), and expose the dev-only IPCs. Copy of focus/register.ts.
//
// The renderer's old insight engine (renderer/src/lib/insightEngine.ts) no longer
// runs its extraction loop — this main-hosted engine replaces it, so exactly ONE
// Insight engine is live and there is never a duplicate toast.
import { ipcMain } from 'electron'
import { is } from '@electron-toolkit/utils'
import { registerAssistant } from '../core/coordinator'
import { latestRewindFrame } from '../../ipc/db'
import { getBackendSession } from '../core/session'
import { getInsightAssistant } from './insightAssistant'
import { migrateInsightPromptIfNeeded } from './promptStore'
import { transportSmoke } from './gemini'

let registered = false

export function registerInsightAssistant(): void {
  if (registered) return
  registered = true

  migrateInsightPromptIfNeeded()
  registerAssistant(getInsightAssistant())

  if (is.dev) {
    // Force one real two-phase extraction of the latest captured frame.
    ipcMain.handle('insight:analyzeNow', async () => {
      const frame = latestRewindFrame()
      if (!frame) return { ok: false, reason: 'no-frame' }
      await getInsightAssistant().analyzeNowForDev(frame)
      return { ok: true }
    })

    // Early transport smoke: confirm the proxy returns a functionCall through the
    // response path and accepts an echoed functionResponse. Never exposed in a
    // shipped build.
    ipcMain.handle('insight:transportSmoke', async () => {
      const session = getBackendSession()
      if (!session) return { ok: false, reason: 'no-session' }
      try {
        const r = await transportSmoke(session)
        return { ok: true, ...r }
      } catch (e) {
        return { ok: false, reason: e instanceof Error ? e.name : 'error' }
      }
    })
  }
}
