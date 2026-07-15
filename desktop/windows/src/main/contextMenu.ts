import { Menu } from 'electron'
import type { BrowserWindow } from 'electron'
import { buildContextMenuTemplate } from './contextMenuTemplate'

/**
 * Give a window Windows' standard right-click editing menu (undo/redo, cut/copy/
 * paste, select all) — native, so it's accessible to Narrator/UIA and follows the
 * OS menu theme. Install on every window the user can type or select text in.
 *
 * Without this, right-clicking anywhere in the app does nothing at all: Electron
 * ships no default context menu.
 */
export function installContextMenu(win: BrowserWindow): void {
  win.webContents.on('context-menu', (_event, params) => {
    const template = buildContextMenuTemplate(params)
    if (!template.length) return
    Menu.buildFromTemplate(template).popup({ window: win })
  })
}
