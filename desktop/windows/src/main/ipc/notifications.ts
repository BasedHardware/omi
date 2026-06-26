import { ipcMain } from 'electron'
import {
  getWindowsNotificationSettings,
  updateWindowsNotificationSettings
} from '../notifications/settings'
import { sendWindowsNotificationTest } from '../notifications/native'
import type {
  WindowsNotificationSettingsPatch,
  WindowsNotificationTestKind
} from '../../shared/types'

export function registerNotificationHandlers(): void {
  ipcMain.handle('notifications:getSettings', async () => getWindowsNotificationSettings())
  ipcMain.handle(
    'notifications:setSettings',
    async (_event, patch: WindowsNotificationSettingsPatch) =>
      updateWindowsNotificationSettings(patch)
  )
  ipcMain.handle('notifications:test', async (_event, kind?: WindowsNotificationTestKind) =>
    sendWindowsNotificationTest(kind)
  )
}
