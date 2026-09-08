import { ipcMain, net, type IpcMainInvokeEvent } from 'electron'
import {
  bulkDeleteMemories,
  type BulkDeleteArgs,
  type BulkDeleteResponse,
  type BulkDeleteResult
} from '../memoryCleanup/bulkDelete'

export type { BulkDeleteArgs, BulkDeleteResult }

// The API base is main-owned config (VITE_OMI_API_BASE, frozen into the main
// bundle at build time — same mechanism as ipc/auth.ts / ipc/byok.ts) and is
// NEVER taken from the renderer: a compromised renderer must not be able to
// redirect these bearer-token requests at an origin it controls.
function apiBase(): string {
  return import.meta.env.VITE_OMI_API_BASE || 'https://api.omi.me'
}

// Bulk-delete memories from the main process so the job survives renderer
// navigation / reloads and never blocks the UI thread. The renderer passes a
// fresh Firebase token + the ids to remove; we delete them through
// DELETE /v3/memories/batch (chunks of ≤100) so concurrent workers cannot
// collide on the account-wide destructive-operation gate.

export function registerMemoryCleanupHandlers(): void {
  ipcMain.handle(
    'memories:bulkDelete',
    async (e: IpcMainInvokeEvent, args: BulkDeleteArgs): Promise<BulkDeleteResult> => {
      console.log(`[memcleanup] starting: ${args.ids.length} ids, token.len=${args.token.length}`)
      const result = await bulkDeleteMemories(
        (url, init) => net.fetch(url, init) as Promise<BulkDeleteResponse>,
        apiBase(),
        args,
        {
          onProgress: ({ deleted, failed, total, done }) => {
            if (!e.sender.isDestroyed()) {
              e.sender.send('memories:deleteProgress', { deleted, failed, total, done })
            }
          }
        }
      )
      console.log(
        `[memcleanup] done: deleted=${result.deleted} failed=${result.failed}${
          result.firstError ? ` firstError="${result.firstError}"` : ''
        }`
      )
      return result
    }
  )
}
