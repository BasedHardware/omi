import { ipcMain } from 'electron'
import type { BeeperSettingsPatch, BeeperStatus } from '../../shared/types'
import { listDrafts } from '../beeper/state'
import {
  connect,
  disconnect,
  dismissDraft,
  getStatus,
  openDownload,
  pollNow,
  sendDraft,
  setSettings,
  syncPoller
} from '../beeper/replyService'
import { probeBeeper } from '../beeper/client'
import { loadBeeperSettings } from '../beeper/settings'
import { getCurrentBeeperDraftToast } from '../insight/toastWindow'

export function registerBeeperHandlers(): void {
  ipcMain.handle('beeper:probe', async () => probeBeeper())
  ipcMain.handle('beeper:connect', async (_e, token: unknown): Promise<BeeperStatus> => {
    if (typeof token !== 'string') throw new Error('token required')
    return connect(token)
  })
  ipcMain.handle('beeper:disconnect', async () => disconnect())
  ipcMain.handle('beeper:status', async () => getStatus())
  ipcMain.handle(
    'beeper:setSettings',
    async (_e, patch: BeeperSettingsPatch): Promise<BeeperStatus> => setSettings(patch ?? {})
  )
  ipcMain.handle('beeper:listDrafts', async () => listDrafts())
  ipcMain.handle('beeper:sendDraft', async (_e, id: unknown) => {
    if (typeof id !== 'string') throw new Error('id required')
    return sendDraft(id)
  })
  ipcMain.handle('beeper:dismissDraft', async (_e, id: unknown) => {
    if (typeof id !== 'string') throw new Error('id required')
    return dismissDraft(id)
  })
  ipcMain.handle('beeper:openDownload', async () => {
    openDownload()
  })
  ipcMain.handle('beeper:pollNow', async () => pollNow())
  ipcMain.handle('beeper:getDraftToast', async () => getCurrentBeeperDraftToast())

  // Resume a previously enabled connection after app launch.
  if (loadBeeperSettings().enabled) syncPoller()
}
