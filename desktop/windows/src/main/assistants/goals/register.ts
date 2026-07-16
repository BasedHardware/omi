// Bring goal auto-generation up: expose the manual `goals:generateNow` IPC the
// Suggest button calls, and start the periodic scheduler. Called once from the
// main bootstrap alongside the other assistants' registration. This is NOT a
// coordinator peer — goal generation is time/event-triggered, not screen-frame
// driven, so it never registers with the AssistantCoordinator.
import { ipcMain } from 'electron'
import { generateGoalNow, startGoalScheduler } from './schedule'
import type { GenerateResult } from './generate'

let registered = false

export function registerGoalGeneration(): void {
  if (registered) return
  registered = true

  // The Suggest button (renderer) → manual generation, bypassing the day/count
  // gates. Returns the outcome so the page can toast + refresh.
  ipcMain.handle('goals:generateNow', async (): Promise<GenerateResult> => generateGoalNow())

  // Startup due-check + the recurring 4h timer (no-op until a session is relayed
  // and the toggle is on).
  startGoalScheduler()
}
