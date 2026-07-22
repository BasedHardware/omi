// Bring goal auto-generation up: expose the manual `goals:generateNow` IPC the
// Suggest button calls, and start the periodic scheduler. Called once from the
// main bootstrap alongside the other assistants' registration. This is NOT a
// coordinator peer — goal generation is time/event-triggered, not screen-frame
// driven, so it never registers with the AssistantCoordinator.
import { ipcMain } from 'electron'
import { getAppSettings, setAppSettings } from '../../appSettings'
import { acceptGoalCandidate, generateGoalCandidateNow, startGoalScheduler } from './schedule'
import type { CandidateResult, GenerateResult, GoalCandidate } from './generate'

let registered = false

export function registerGoalGeneration(): void {
  if (registered) return
  registered = true

  // The "Automatically suggest goals" toggle (Settings → Proactive insights).
  // A minimal goals-scoped read/write over the appSettings flag — no generic
  // settings bridge. Default OFF (opt-in).
  ipcMain.handle(
    'goals:getAutoGenerationEnabled',
    (): boolean => getAppSettings().goalAutoGenerationEnabled
  )
  ipcMain.handle(
    'goals:setAutoGenerationEnabled',
    (_e, enabled: boolean): boolean =>
      setAppSettings({ goalAutoGenerationEnabled: enabled === true }).goalAutoGenerationEnabled
  )

  // The Suggest button, phase 1 (renderer) → GENERATE a candidate to preview,
  // bypassing the day/count gates. Returns the candidate (or a skip) to preview.
  ipcMain.handle(
    'goals:generateCandidate',
    async (): Promise<CandidateResult> => generateGoalCandidateNow()
  )

  // Phase 2 → the user accepted the preview: CREATE the goal + notify + refresh.
  ipcMain.handle(
    'goals:createCandidate',
    async (_e, candidate: GoalCandidate): Promise<GenerateResult> => acceptGoalCandidate(candidate)
  )

  // Startup due-check + the recurring 4h timer (no-op until a session is relayed
  // and the toggle is on).
  startGoalScheduler()
}
