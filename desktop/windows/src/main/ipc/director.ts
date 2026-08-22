/**
 * Director IPC surface:
 * - `director:setDeviceId` (send): the renderer relays its stable install-id
 *   hash so main-side snapshot calls share the renderer's device scope.
 * - `director:bindRecentContext` (invoke): the renderer reports a
 *   recommendation open so the subject-binding service can bind the most
 *   recent learnable context (mac: DashboardIntelligenceStore.openRecommendation
 *   -> bindRecentContext).
 */

import { ipcMain } from 'electron'
import { setDirectorDeviceIdHash, directorSubjectBinding } from '../assistants/director/service'

export function registerDirectorHandlers(): void {
  ipcMain.on('director:setDeviceId', (_event, hash: unknown) => {
    if (typeof hash === 'string') setDirectorDeviceIdHash(hash)
  })

  ipcMain.handle('director:bindRecentContext', (_event, subject: unknown): boolean => {
    if (typeof subject !== 'object' || subject === null) return false
    const raw = subject as Record<string, unknown>
    if (typeof raw.kind !== 'string' || typeof raw.id !== 'string') return false
    const workstreamID = typeof raw.workstreamID === 'string' ? raw.workstreamID : null
    return directorSubjectBinding.bindRecentContext({ kind: raw.kind, id: raw.id, workstreamID })
  })
}
