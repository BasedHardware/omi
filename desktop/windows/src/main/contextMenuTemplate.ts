import type { ContextMenuParams, MenuItemConstructorOptions } from 'electron'

// Pure builder for the app's right-click menu. Kept separate from the Electron
// wiring (contextMenu.ts) so it can be unit-tested without an Electron runtime —
// same split as bar/placement.ts (pure) vs bar/window.ts (wiring).
//
// Why a NATIVE menu and not a DOM one: a DOM context menu is invisible to Windows
// accessibility (Narrator/UIA see a div, not a menu), doesn't honour the OS menu
// theme or animation, and can't outlive its window's bounds. Chromium's own menu,
// built from ROLES, gets all of that for free — and roles route to the focused
// webContents' real editing commands, so cut/copy/paste work in every input,
// including the chat composer, with correct enable/disable state.

// Only the bits of ContextMenuParams this builder reads. Lets tests construct a
// params object without faking Electron's full (large) interface.
export type ContextMenuInput = Pick<ContextMenuParams, 'isEditable' | 'selectionText' | 'editFlags'>

/**
 * The menu for a right-click, or [] when there is nothing useful to offer (a
 * right-click on a non-editable area with no selection) — the caller must not
 * pop up an empty menu.
 *
 * Items are role-based, so Chromium performs the action against the focused
 * webContents and greys out what isn't currently possible. We still filter on
 * editFlags rather than showing everything disabled: a menu of five dead items
 * is noise, and Windows apps conventionally hide inapplicable edit commands.
 */
export function buildContextMenuTemplate(params: ContextMenuInput): MenuItemConstructorOptions[] {
  const flags = params.editFlags
  const hasSelection = params.selectionText.trim().length > 0

  // Read-only surface (a message bubble, a transcript, a label). Copying the
  // selection is the only sensible action; Select All is offered so keyboard and
  // mouse users can grab the whole block.
  if (!params.isEditable) {
    if (!hasSelection) return []
    const items: MenuItemConstructorOptions[] = [{ role: 'copy' }]
    if (flags.canSelectAll) items.push({ type: 'separator' }, { role: 'selectAll' })
    return items
  }

  // Editable field (chat composer, search box, settings input).
  const items: MenuItemConstructorOptions[] = []
  if (flags.canUndo) items.push({ role: 'undo' })
  if (flags.canRedo) items.push({ role: 'redo' })

  const edit: MenuItemConstructorOptions[] = []
  if (flags.canCut) edit.push({ role: 'cut' })
  if (flags.canCopy) edit.push({ role: 'copy' })
  if (flags.canPaste) edit.push({ role: 'paste' })
  if (edit.length) {
    if (items.length) items.push({ type: 'separator' })
    items.push(...edit)
  }

  if (flags.canSelectAll) {
    if (items.length) items.push({ type: 'separator' })
    items.push({ role: 'selectAll' })
  }

  return items
}
