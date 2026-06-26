import { Notification, app, desktopCapturer, ipcMain, shell, systemPreferences } from 'electron'
import { checkWindowsUpdaterNow, getWindowsUpdateStatus, updatesEnabled } from '../updater'
import type { WindowsExternalLinkKind, WindowsSystemStatus } from '../../shared/types'

const LINKS: Record<WindowsExternalLinkKind, string> = {
  help: 'https://github.com/BasedHardware/omi/issues',
  browserExtension: 'https://github.com/BasedHardware/omi',
  releaseNotes: 'https://github.com/BasedHardware/omi/releases',
  windowsStartupSettings: 'ms-settings:startupapps',
  windowsMicrophoneSettings: 'ms-settings:privacy-microphone',
  windowsNotificationSettings: 'ms-settings:notifications',
  windowsPrivacySettings: 'ms-settings:privacy'
}

function micStatus(): WindowsSystemStatus['microphone'] {
  try {
    const status = systemPreferences.getMediaAccessStatus('microphone')
    if (status === 'granted' || status === 'denied' || status === 'not-determined') return status
  } catch {
    /* unsupported platform/API */
  }
  return 'unknown'
}

async function screenStatus(): Promise<WindowsSystemStatus['screenCapture']> {
  try {
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 1, height: 1 }
    })
    return sources.length > 0 ? 'granted' : 'unknown'
  } catch {
    return 'denied'
  }
}

async function systemStatus(): Promise<WindowsSystemStatus> {
  const login = app.getLoginItemSettings()
  return {
    launchAtLogin: login.openAtLogin,
    microphone: micStatus(),
    screenCapture: await screenStatus(),
    notificationsSupported: Notification.isSupported(),
    packaged: app.isPackaged || updatesEnabled()
  }
}

export function registerSystemHandlers(): void {
  ipcMain.handle('system:getStatus', async () => systemStatus())
  ipcMain.handle('system:setLaunchAtLogin', async (_event, enabled: boolean) => {
    app.setLoginItemSettings({ openAtLogin: !!enabled })
    return systemStatus()
  })
  ipcMain.handle('system:openExternal', async (_event, kind: WindowsExternalLinkKind) => {
    const url = LINKS[kind]
    if (!url) throw new Error('Unknown system link')
    await shell.openExternal(url)
  })
  ipcMain.handle('updater:getStatus', async () => getWindowsUpdateStatus())
  ipcMain.handle('updater:checkNow', async () => checkWindowsUpdaterNow())
}
