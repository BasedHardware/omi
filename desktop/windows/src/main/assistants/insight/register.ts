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
import { latestRewindFrame, rewindActivityAggregate, runReadonlySelect } from '../../ipc/db'
import { getBackendSession } from '../core/session'
import { getInsightAssistant } from './insightAssistant'
import { migrateInsightPromptIfNeeded } from './promptStore'
import { transportSmoke } from './gemini'
import { executeSql } from './sql'
import { getInsightSettings } from '../../insight/state'
import { getAppSettings, setAppSettings } from '../../appSettings'

/** Turn executeSql's Gemini-facing pipe-table string into a bare row count, never
 *  surfacing a cell. `No results` → 0, a table's trailing `N row(s)` → N, an
 *  `Error: …` rejection → rowCount -1 with the (content-free) message. */
function parseSqlRowCount(out: string): { rowCount: number; error?: string } {
  if (out.startsWith('Error:')) return { rowCount: -1, error: out }
  if (out === 'No results') return { rowCount: 0 }
  const m = out.match(/(\d+) row\(s\)\s*$/)
  return { rowCount: m ? parseInt(m[1], 10) : -1 }
}

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

    // Observability for the FIX 4 denylist exclusion: run the REAL Phase-1 activity
    // aggregate (rewindActivityAggregate) over the last 24h with the caller's
    // denylist and return ONLY the distinct app names — never ocr_text or window
    // titles (app names are not sensitive). Proves a denylisted app is excluded at
    // the SQL layer before anything could reach Gemini.
    ipcMain.handle('insight:debugActivity', async (_e, denylist: string[] = []) => {
      const now = Date.now()
      const rows = rewindActivityAggregate(now - 24 * 60 * 60_000, now, 50, denylist ?? [])
      const apps = [...new Set(rows.map((r) => r.app))]
      return { apps, rowCount: rows.length }
    })

    // Observability for the FIX 4 execute_sql denylist shadow: run the REAL
    // sql.ts executeSql closure with the caller's denylist and return ONLY the row
    // count (or the content-free error string) — never a cell. Proves the CTE-shadow
    // filters a denylisted app to zero rows.
    ipcMain.handle('insight:debugSql', async (_e, query: string, denylist: string[] = []) => {
      const out = executeSql(query, runReadonlySelect, denylist ?? [])
      return parseSqlRowCount(out)
    })

    // Observability for the FIX 5 silent-gate: optionally apply a notifications
    // patch (so both Off and non-Off states can be exercised), then return the REAL
    // insightAssistant.isEnabled() alongside the three inputs that decide it.
    ipcMain.handle(
      'insight:debugIsEnabled',
      async (_e, patch?: { notificationsEnabled?: boolean; notificationFrequency?: number }) => {
        if (patch) setAppSettings(patch)
        const settings = getAppSettings()
        return {
          isEnabled: getInsightAssistant().isEnabled(),
          insightEnabled: getInsightSettings().enabled,
          notificationsEnabled: settings.notificationsEnabled,
          notificationFrequency: settings.notificationFrequency
        }
      }
    )
  }
}
