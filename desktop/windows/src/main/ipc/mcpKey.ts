import { ipcMain } from 'electron'
import type { McpKeyRecord } from '../../shared/types'
import { clearMcpKey, loadMcpKey, saveMcpKey } from '../integrations/mcpKeyStore'

export function registerMcpKeyHandlers(): void {
  ipcMain.handle('mcpKey:create', async (_e, record: McpKeyRecord): Promise<void> => {
    saveMcpKey(record)
  })

  ipcMain.handle('mcpKey:read', async (): Promise<McpKeyRecord | null> => loadMcpKey())

  ipcMain.handle('mcpKey:delete', async (): Promise<void> => {
    clearMcpKey()
  })
}
