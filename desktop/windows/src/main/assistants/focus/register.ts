// Bring the Focus assistant up: migrate its prompt version, register it with the
// coordinator (which starts the shared analysis loop if the master toggle is on),
// and expose the dev-only `focus:analyzeNow` IPC.
//
// Registering the assistant is what starts the coordinator — "no assistants, no
// polling." So this is the single call that turns the whole proactive stack on.
import { ipcMain } from 'electron'
import { is } from '@electron-toolkit/utils'
import { registerAssistant } from '../core/coordinator'
import { latestRewindFrame } from '../../ipc/db'
import { getFocusAssistant } from './focusAssistant'
import { migrateFocusPromptIfNeeded } from './promptStore'

let registered = false

export function registerFocusAssistant(): void {
  if (registered) return
  registered = true

  migrateFocusPromptIfNeeded()
  registerAssistant(getFocusAssistant())

  // Dev/QA: force one analysis of the latest captured frame, so the pipeline can
  // be exercised (and the halo seen) without waiting for a natural context
  // switch. Non-prod only — never expose an on-demand cloud vision call in a
  // shipped build.
  if (is.dev) {
    ipcMain.handle('focus:analyzeNow', async () => {
      const frame = latestRewindFrame()
      if (!frame) return { ok: false, reason: 'no-frame' }
      await getFocusAssistant().analyzeNowForDev(frame)
      return { ok: true }
    })
  }
}
