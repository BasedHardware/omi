import { Menu, clipboard, shell } from 'electron'
import type { BrowserWindow } from 'electron'
import { LINK_SCHEMES } from '../contextMenuTemplate'
import { isAllowedExternalScheme } from '../externalUrl'
import { setNotificationSnooze } from '../assistants/core/notify'
import { BAR_SNOOZE_MS, buildBarContextMenuTemplate } from './barContextMenuTemplate'

/**
 * Give the floating bar window a native right-click menu — the standard editing/
 * selection/link items plus a bar-level "Disable for 2 hours" snooze. Port of
 * macOS `FloatingControlBarView.barContextMenu`; the bar previously had NO
 * context menu at all (right-clicking it did nothing).
 *
 * Bar-scoped on purpose: the snooze is only meaningful on the floating bar, so
 * it is NOT added via the shared `installContextMenu` that the main and checkout
 * windows use. Kept as thin wiring over the pure `buildBarContextMenuTemplate`
 * (the split mirrors contextMenu.ts / contextMenuTemplate.ts) so the menu logic
 * stays unit-testable without an Electron runtime.
 */
export function installBarContextMenu(win: BrowserWindow): void {
  win.webContents.on('context-menu', (_event, params) => {
    const template = buildBarContextMenuTemplate(params, {
      copyText: (text) => clipboard.writeText(text),
      // Same scheme guard installContextMenu applies: a chat link can be steered
      // by prompt injection to a file://, UNC, or custom-protocol URL, and handing
      // those to the OS enables NTLM-hash leak / protocol abuse — only http/https
      // reach the browser. Never log the raw URL (it may carry a token).
      openExternal: (url) => {
        if (isAllowedExternalScheme(url, LINK_SCHEMES)) shell.openExternal(url)
        else console.warn('[bar] blocked context-menu open of a non-web link')
      },
      // "Disable for 2 hours" — silence proactive notifications, mirroring Mac's
      // FloatingControlBarManager.snooze(for: snoozeTwoHoursDuration).
      snooze: () => setNotificationSnooze(Date.now() + BAR_SNOOZE_MS)
    })
    // The snooze is always present, so this is never empty — but keep the guard so
    // an empty template (should it ever happen) never pops a blank menu.
    if (!template.length) return
    Menu.buildFromTemplate(template).popup({ window: win })
  })
}
