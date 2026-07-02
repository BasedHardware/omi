import { Tray, Menu, nativeImage, app, dialog } from 'electron'
import { createMainWindow, toggleFloatingBar, getFloatingBar, getMainWindow } from './windows'
import { settings } from './settings'
import { resourcePath } from './resources'
import { checkForUpdates } from './updater'

// Mirrors the NSStatusBar menu in OmiApp.swift:setupMenuBar().
//
// Linux note: the tray uses StatusNotifierItem/AppIndicator (with GtkStatusIcon
// fallback). The Tray 'double-click' event does NOT fire on Linux, and 'click'
// only fires on an environment-defined "activation" gesture that is not
// guaranteed to be a single left-click. So every action must be reachable from
// the right-click context menu via setContextMenu (see rebuildTrayMenu); the
// left-click handler below is only a best-effort convenience.

let tray: Tray | null = null

export function rebuildTrayMenu(): void {
  if (!tray) return
  const s = settings.get()
  const floatingVisible = getFloatingBar()?.isVisible() ?? false
  const menu = Menu.buildFromTemplate([
    {
      label: floatingVisible ? 'Hide Floating Bar' : 'Show Floating Bar',
      click: () => {
        toggleFloatingBar()
        rebuildTrayMenu()
      }
    },
    {
      label: 'Screen Capture',
      type: 'checkbox',
      checked: s.rewindEnabled,
      click: (item) => {
        settings.set({ rewindEnabled: item.checked })
        rebuildTrayMenu()
      }
    },
    {
      label: 'Audio Recording',
      click: () => {
        const win = createMainWindow()
        win.webContents.send('app:navigate', 'conversations')
      }
    },
    { type: 'separator' },
    { label: 'Open Omi', click: () => createMainWindow() },
    {
      label: 'Settings',
      click: () => {
        const win = createMainWindow()
        win.webContents.send('app:navigate', 'settings')
      }
    },
    {
      label: 'Rewind',
      click: () => {
        const win = createMainWindow()
        win.webContents.send('app:navigate', 'rewind')
      }
    },
    { type: 'separator' },
    {
      label: 'Check for Updates',
      click: () => void checkForUpdates(true)
    },
    {
      label: 'About omi',
      click: async () => {
        const options = {
          type: 'info',
          message: `omi for Linux`,
          detail: `Version ${app.getVersion()}\nYour AI that remembers everything.`
        } as const
        const parent = getMainWindow()
        if (parent) await dialog.showMessageBox(parent, options)
        else await dialog.showMessageBox(options)
      }
    },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() }
  ])
  tray.setContextMenu(menu)
}

export function createTray(): Tray {
  if (tray) return tray
  let icon = nativeImage.createFromPath(resourcePath('tray_icon.png'))
  if (icon.isEmpty()) console.error('tray: icon resource missing or unreadable')
  else icon = icon.resize({ width: 16, height: 16 })
  tray = new Tray(icon)
  tray.setToolTip('omi')
  // On Linux 'double-click' never fires; 'click' fires only on the desktop
  // environment's activation gesture. Bind 'click' as a best-effort shortcut to
  // open the main window, but all actions remain available via the context menu
  // (setContextMenu in rebuildTrayMenu), which is the reliable entry point.
  tray.on('click', () => createMainWindow())
  rebuildTrayMenu()
  return tray
}
