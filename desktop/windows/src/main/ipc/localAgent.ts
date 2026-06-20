import { ipcMain } from 'electron'
import type { LocalAgentStatus, LocalAgentToolsTestResult } from '../../shared/types'
import {
  copyLocalAgentToken,
  getLocalAgentStatus,
  rotateLocalAgentAccessToken,
  setLocalAgentEnabled,
  setLocalAgentPort,
  testLocalAgentTools
} from '../localAgent/control'

export function registerLocalAgentHandlers(): void {
  ipcMain.handle('localAgent:status', async (): Promise<LocalAgentStatus> => getLocalAgentStatus())
  ipcMain.handle(
    'localAgent:setEnabled',
    async (_e, enabled: boolean): Promise<LocalAgentStatus> =>
      setLocalAgentEnabled(enabled === true)
  )
  ipcMain.handle(
    'localAgent:setPort',
    async (_e, port: number): Promise<LocalAgentStatus> => setLocalAgentPort(port)
  )
  ipcMain.handle(
    'localAgent:copyToken',
    async (): Promise<LocalAgentStatus> => copyLocalAgentToken()
  )
  ipcMain.handle(
    'localAgent:rotateToken',
    async (): Promise<LocalAgentStatus> => rotateLocalAgentAccessToken()
  )
  ipcMain.handle(
    'localAgent:testTools',
    async (): Promise<LocalAgentToolsTestResult> => testLocalAgentTools()
  )
}
