// IPC surface for BYOK key management. Follows the house invoke-handler pattern
// (see `codingAgent.ts`). The store is main-process only; these handlers are the
// renderer's Settings UI seam onto it.
//
// SECURITY NOTE: `byok:getAll` returns raw key material to the renderer. That is
// acceptable here — the renderer is the app's own Settings surface (same trust
// model as the app process), and the keys must be shown/edited there. Do NOT
// expose these channels to untrusted web content, and never log key values.

import { ipcMain, webContents } from 'electron'
import { ByokKeyStore } from '../agentKernel/byokStore'
import { deactivateByok, enrollByok, type ByokEnrollResult } from '../agentKernel/byokEnroll'
import type { ByokKeys, ByokProvider } from '../../shared/byok'

let store: ByokKeyStore | null = null

// Lazily construct on first use so the module stays import-pure (no app.getPath
// at import time — userData isn't ready until the app is).
function getStore(): ByokKeyStore {
  if (!store) store = new ByokKeyStore()
  return store
}

function apiBase(): string {
  return import.meta.env.VITE_OMI_API_BASE || 'https://api.omi.me'
}

/**
 * Tell every renderer that the BYOK key set or activation changed, so the
 * in-memory key cache backing the axios/fetch header lanes reloads and any
 * plan/usage surface refetches. Carries no key material — just a ping.
 */
function broadcastByokChanged(): void {
  for (const wc of webContents.getAllWebContents()) {
    if (!wc.isDestroyed()) wc.send('byok:changed')
  }
}

/** Registers the `byok:*` IPC handlers backing the ByokKeyStore. */
export function registerByokHandlers(): void {
  ipcMain.handle('byok:getAll', (): ByokKeys => getStore().getAllKeys())
  ipcMain.handle('byok:set', (_e, provider: ByokProvider, key: string): void => {
    getStore().setKey(provider, key)
    broadcastByokChanged()
  })
  ipcMain.handle('byok:clear', (_e, provider: ByokProvider): void => {
    getStore().clearKey(provider)
    broadcastByokChanged()
  })
  ipcMain.handle('byok:clearAll', (): void => {
    getStore().clearAll()
    broadcastByokChanged()
  })
  ipcMain.handle('byok:isActive', (): boolean => getStore().isActive())

  // Validate the stored keys live and reconcile the backend BYOK activation.
  // The Firebase bearer token is relayed from the renderer (same pattern as the
  // listen WebSocket) since the token lives in the renderer's Firebase session.
  ipcMain.handle('byok:enroll', async (_e, token: string): Promise<ByokEnrollResult> => {
    const result = await enrollByok({
      keys: getStore().getAllKeys(),
      apiBase: apiBase(),
      token
    })
    broadcastByokChanged()
    return result
  })

  // Sign-out: drop the backend enrollment (the local store is cleared separately
  // by the teardown path). Best-effort; the token is relayed from the renderer
  // while the session is still valid.
  ipcMain.handle('byok:deactivate', async (_e, token: string): Promise<void> => {
    await deactivateByok({ apiBase: apiBase(), token })
  })
}
