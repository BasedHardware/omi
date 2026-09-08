// Bring the Memory assistant up: register it with the coordinator (which starts
// the shared analysis loop if the master toggle is on) and expose the dev-only
// IPCs. Mirrors focus/register.ts and insight/register.ts. There is no prompt
// migration to run — Mac's memory prompt has no version constant.
import { ipcMain } from 'electron'
import { is } from '@electron-toolkit/utils'
import { registerAssistant } from '../core/coordinator'
import { latestRewindFrame } from '../../ipc/db'
import { getAppSettings } from '../../appSettings'
import { getMemoryAssistant } from './memoryAssistant'

let registered = false

export function registerMemoryAssistant(): void {
  if (registered) return
  registered = true

  registerAssistant(getMemoryAssistant())

  if (is.dev) {
    // Force one real extraction of the latest captured frame, so the pipeline can
    // be exercised without waiting for the extraction interval. Non-prod only —
    // never expose an on-demand cloud vision call in a shipped build.
    ipcMain.handle('memory:analyzeNow', async () => {
      const frame = latestRewindFrame()
      if (!frame) return { ok: false, reason: 'no-frame' }
      await getMemoryAssistant().analyzeNowForDev(frame)
      return { ok: true }
    })

    // Observability for the gate: the REAL isEnabled() (decided solely by
    // memoryEnabled) alongside the coordinator's master screen-analysis lever,
    // which gates whether the loop runs at all.
    ipcMain.handle('memory:debugIsEnabled', async () => {
      const settings = getAppSettings()
      return {
        isEnabled: getMemoryAssistant().isEnabled(),
        memoryEnabled: settings.memoryEnabled,
        screenAnalysisEnabled: settings.screenAnalysisEnabled
      }
    })
  }
}
