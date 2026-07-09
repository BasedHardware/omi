// IPC surface for delegated coding-agent tasks. Follows the house pattern:
// invoke-style handlers plus a broadcast channel for streaming task events
// (both the main window and the overlay may render the same task's progress).

import { ipcMain, BrowserWindow } from 'electron'
import {
  ADAPTER_PROFILES,
  adapterActivationError,
  adapterIsActivated,
  type AdapterCommandOverrides
} from '../codingAgent/adapterRegistry'
import { PRODUCTION_ADAPTER_IDS } from '../codingAgent/interface'
import { cancelTask, runCodingAgentTask } from '../codingAgent/taskRunner'
import type {
  CodingAgentEvent,
  CodingAgentInfo,
  CodingAgentResult,
  CodingAgentRunArgs
} from '../../shared/types'

function broadcast(event: CodingAgentEvent): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send('codingAgent:event', event)
    }
  }
}

export function registerCodingAgentHandlers(): void {
  ipcMain.handle(
    'codingAgent:list',
    (_e, commandOverrides?: AdapterCommandOverrides): CodingAgentInfo[] => {
      const overrides = commandOverrides ?? {}
      return PRODUCTION_ADAPTER_IDS.map((id) => {
        const connected = adapterIsActivated(id, overrides)
        return {
          id,
          displayName: ADAPTER_PROFILES[id].displayName,
          connected,
          installHint: connected ? undefined : adapterActivationError(id)
        }
      })
    }
  )

  ipcMain.handle(
    'codingAgent:run',
    (_e, args: CodingAgentRunArgs): Promise<CodingAgentResult> =>
      runCodingAgentTask(args, broadcast, (message) => console.log(`[codingAgent] ${message}`))
  )

  ipcMain.handle('codingAgent:cancel', (_e, taskId: string): boolean => cancelTask(taskId))
}
