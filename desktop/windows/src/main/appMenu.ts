import { Menu } from 'electron'

/**
 * Remove Electron's stock application menu.
 *
 * index.ts only sets `autoHideMenuBar: true`, which merely hides the default menu
 * behind Alt — in a packaged build an end user can still press Alt and reach
 * Reload / Force Reload / **Toggle DevTools**. The app draws no menu bar of its
 * own, so we drop the menu entirely, matching Mac's curated (DevTools-free) menu.
 *
 * This is safe to remove because nothing the app relies on lives on that menu:
 * - Native edit shortcuts (Ctrl+C/V/X/Z/Y, Ctrl+A) are Chromium built-ins, not
 *   menu accelerators — they keep working in every input (the same reason the
 *   role-based contextMenuTemplate can offer cut/copy/paste without an app menu).
 * - The app's own shortcuts (Ctrl+1–6, Ctrl+,, Ctrl+= / - / 0, Ctrl+W, Ctrl+Q)
 *   are handled by renderer keydown + the window's before-input-event, never the
 *   menu.
 * - Dev DevTools stays reachable via `optimizer.watchWindowShortcuts` (F12 /
 *   Ctrl+Shift+I), which is a keyboard shortcut, not the menu — so this only
 *   removes the *menu's* Toggle DevTools, not the dev shortcut.
 *
 * Extracted from the app-ready path so the one call is unit-testable without
 * booting the app, mirroring the other small main-process modules.
 */
export function disableApplicationMenu(): void {
  Menu.setApplicationMenu(null)
}
