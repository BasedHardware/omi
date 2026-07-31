import { Menu, clipboard, shell } from 'electron'
import type { BrowserWindow } from 'electron'
import { buildContextMenuTemplate, LINK_SCHEMES } from './contextMenuTemplate'
import { isAllowedExternalScheme } from './externalUrl'

/**
 * Give a window Windows' standard right-click menu — editing (undo/redo, cut/copy/
 * paste, select all) plus, on a hyperlink, Open Link / Copy Link Address. Native,
 * so it's accessible to Narrator/UIA and follows the OS menu theme. Install on
 * every window the user can type, select text, or click a link in.
 *
 * Without this, right-clicking anywhere in the app does nothing at all: Electron
 * ships no default context menu.
 */
export function installContextMenu(win: BrowserWindow): void {
  win.webContents.on('context-menu', (_event, params) => {
    const template = buildContextMenuTemplate(params, {
      copyText: (text) => clipboard.writeText(text),
      // Same guard index.ts applies before every shell.openExternal: a chat link
      // can be steered by prompt injection to a file://, UNC, or custom-protocol
      // URL, and handing those to the OS enables NTLM-hash leak / protocol abuse.
      // The builder already gates the menu item on this list; validating again
      // here keeps the OS hand-off safe on its own terms. Never navigates the app
      // window — the link opens in the user's default browser.
      openExternal: (url) => {
        if (isAllowedExternalScheme(url, LINK_SCHEMES)) shell.openExternal(url)
        // Never log the raw URL — it may carry a token/secret in its query string.
        else console.warn('[main] blocked context-menu open of a non-web link')
      }
    })
    if (!template.length) return
    Menu.buildFromTemplate(template).popup({ window: win })
  })
}
