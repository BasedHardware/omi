// IPC surface for BYOK key management. Follows the house invoke-handler pattern
// (see `codingAgent.ts`). The store is main-process only; these handlers are the
// renderer's Settings UI seam onto it.
//
// SECURITY NOTE: `byok:getAll` returns raw key material to the renderer. That is
// acceptable here — the renderer is the app's own Settings surface (same trust
// model as the app process), and the keys must be shown/edited there. Do NOT
// expose these channels to untrusted web content, and never log key values.

import { ipcMain } from 'electron'
import { ByokKeyStore } from '../agentKernel/byokStore'
import type { ByokKeys, ByokProvider } from '../../shared/byok'

let store: ByokKeyStore | null = null

// Lazily construct on first use so the module stays import-pure (no app.getPath
// at import time — userData isn't ready until the app is).
function getStore(): ByokKeyStore {
  if (!store) store = new ByokKeyStore()
  return store
}

/** Registers the `byok:*` IPC handlers backing the ByokKeyStore. */
export function registerByokHandlers(): void {
  ipcMain.handle('byok:getAll', (): ByokKeys => getStore().getAllKeys())
  ipcMain.handle('byok:set', (_e, provider: ByokProvider, key: string): void =>
    getStore().setKey(provider, key)
  )
  ipcMain.handle('byok:clear', (_e, provider: ByokProvider): void => getStore().clearKey(provider))
  ipcMain.handle('byok:clearAll', (): void => getStore().clearAll())
  ipcMain.handle('byok:isActive', (): boolean => getStore().isActive())
}
