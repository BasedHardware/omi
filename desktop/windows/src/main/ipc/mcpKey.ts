import { ipcMain } from 'electron'
import type { McpKeyRecord } from '../../shared/types'
import { clearMcpKey, loadMcpKey, saveMcpKey } from '../integrations/mcpKeyStore'
import { addObservabilityBreadcrumb, captureMainException } from '../observability'

export function registerMcpKeyHandlers(): void {
  ipcMain.handle('mcpKey:create', async (_e, record: McpKeyRecord): Promise<void> => {
    addObservabilityBreadcrumb(
      'mcp_key.create_requested',
      { hasId: Boolean(record?.id), nameLength: record?.name?.length ?? 0 },
      { category: 'mcp' }
    )
    try {
      saveMcpKey(record)
      addObservabilityBreadcrumb('mcp_key.create_finished', { ok: true }, { category: 'mcp' })
    } catch (error) {
      captureMainException('mcp_key.create_failed', error, {
        hasId: Boolean(record?.id),
        nameLength: record?.name?.length ?? 0
      })
      throw error
    }
  })

  ipcMain.handle('mcpKey:read', async (): Promise<McpKeyRecord | null> => loadMcpKey())

  ipcMain.handle('mcpKey:delete', async (): Promise<void> => {
    clearMcpKey()
    addObservabilityBreadcrumb('mcp_key.deleted', {}, { category: 'mcp' })
  })
}
