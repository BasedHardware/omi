import type { MenuItemConstructorOptions } from 'electron'
import {
  buildContextMenuTemplate,
  type ContextMenuDeps,
  type ContextMenuInput
} from '../contextMenuTemplate'

// The floating bar's right-click snooze, ported from macOS FloatingControlBarView's
// `barContextMenu` ("Disable for 2 hours" → FloatingControlBarManager.snooze). Two
// hours in ms — Mac's `snoozeTwoHoursDuration`.
export const BAR_SNOOZE_MS = 2 * 60 * 60 * 1000

// Windows' snooze silences proactive NOTIFICATIONS (setNotificationSnooze), not
// the bar itself, so the label says so plainly — a touch more explicit than Mac's
// "Disable for 2 hours" while porting the same affordance.
export const BAR_SNOOZE_LABEL = 'Disable notifications for 2 hours'

export type BarContextMenuDeps = ContextMenuDeps & {
  /** Silence proactive notifications for a fixed window (the snooze item's action). */
  snooze: () => void
}

/**
 * The floating bar's right-click menu: the app's standard editing/selection/link
 * menu (via the SHARED builder — no drift with the rest of the app) plus a
 * bar-level "Disable for 2 hours" snooze that is always offered. Ported from
 * macOS `FloatingControlBarView.barContextMenu`.
 *
 * Bar-scoped by construction: the snooze lives here, not in the shared
 * `buildContextMenuTemplate`, so it can never appear on the main / checkout
 * windows. The snooze is always present — a right-click on the empty bar still
 * offers it — so this never returns [] and the caller always has a menu to pop.
 */
export function buildBarContextMenuTemplate(
  params: ContextMenuInput,
  deps: BarContextMenuDeps
): MenuItemConstructorOptions[] {
  const base = buildContextMenuTemplate(params, deps)
  const snooze: MenuItemConstructorOptions = {
    label: BAR_SNOOZE_LABEL,
    click: () => deps.snooze()
  }
  // A single separator joins the two groups only when the editing/link menu is
  // non-empty — preserving the "never leading/trailing/doubled separator" rule.
  if (!base.length) return [snooze]
  return [...base, { type: 'separator' }, snooze]
}
