import { basename } from 'path'

// Pure target-selection logic, split out from foregroundTarget.ts (which pulls
// in electron + native koffi) so it can be unit-tested under node Vitest.

// True when an exe path belongs to our own app (so we must NOT treat it as a
// target). Compared by basename, case-insensitively — in dev both Omi and the
// inspector share electron.exe, which is fine: we just won't target ourselves.
export function isSelfExe(exePath: string | null, selfExe: string): boolean {
  if (!exePath) return false
  return basename(exePath).toLowerCase() === basename(selfExe).toLowerCase()
}

// Window classes of the Windows shell surfaces (desktop, taskbar, Start/search,
// tray overflow). These are owned by explorer.exe / shell hosts and briefly take
// the foreground when the user clicks the taskbar, Alt-Tabs, or opens Start — but
// they have no actionable UIA tree, so we must never adopt one as the automation
// target (doing so left the planner snapshotting an empty window). A real File
// Explorer FOLDER window is also explorer.exe but uses CabinetWClass, so this
// class-based filter keeps File Explorer while rejecting the bare shell.
const SHELL_WINDOW_CLASSES = new Set([
  'progman', // desktop
  'workerw', // desktop wallpaper layer
  'shell_traywnd', // primary taskbar
  'shell_secondarytraywnd', // taskbar on additional monitors
  'notifyiconoverflowwindow', // tray overflow flyout
  'windows.ui.core.corewindow', // Start menu / search / action center
  'foregroundstaging', // transient window explorer creates mid foreground-switch
  'xamlexplorerhostislandwindow' // Alt-Tab switcher / Task View / virtual desktops
])

export function isShellWindow(className: string | null | undefined): boolean {
  if (!className) return false
  return SHELL_WINDOW_CLASSES.has(className.trim().toLowerCase())
}

// Decide the remembered target: keep the previous handle when the current
// foreground is our own window, a bare shell surface, or we couldn't read a
// handle; otherwise adopt it.
export function pickTarget(
  current: { handle: string | null; exePath: string | null; className?: string | null },
  selfExe: string,
  prev: string | null
): string | null {
  if (!current.handle) return prev
  if (isSelfExe(current.exePath, selfExe)) return prev
  if (isShellWindow(current.className)) return prev
  return current.handle
}
