// IPC for chat-privacy toggles that live in main's app settings.
//
// Currently just "Screen Sharing in Chat" (chatScreenshotSharingEnabled) — the
// consent gate the `capture_screen` tool reads at dispatch (captureScreenExecutor
// .ts). Mirrors the meeting:getSettings / meeting:setSettings shape: read/write a
// single persisted flag, returning the sanitized value so the renderer stays in
// sync with what was actually stored.

import { ipcMain } from 'electron'
import { getAppSettings, setAppSettings } from '../appSettings'

export function registerChatPrivacyHandlers(): void {
  ipcMain.handle(
    'chat:getScreenshotSharing',
    async () => getAppSettings().chatScreenshotSharingEnabled
  )
  ipcMain.handle(
    'chat:setScreenshotSharing',
    async (_e, enabled: boolean) =>
      setAppSettings({ chatScreenshotSharingEnabled: enabled === true })
        .chatScreenshotSharingEnabled
  )
}
