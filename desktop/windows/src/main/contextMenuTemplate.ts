import type {
  BaseWindow,
  BrowserWindow,
  ContextMenuParams,
  MenuItemConstructorOptions
} from 'electron'
import { isAllowedExternalScheme } from './externalUrl'

// Electron types a menu click's window as BaseWindow, which has no webContents.
// Every window we install this menu on is a BrowserWindow (see contextMenu.ts), so
// narrowing is safe — and it keeps this module free of a runtime electron import,
// which is what lets it be unit-tested without an Electron runtime.
const asBrowserWindow = (win: BaseWindow | undefined): BrowserWindow | undefined =>
  win as BrowserWindow | undefined

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

// Schemes a right-clicked link may be opened with. http/https only: a chat reply
// can be steered by indirect prompt injection (the prompt includes OCR of the
// user's screen) to emit a file://, UNC (\\host\share), or custom-protocol href,
// and handing those to the OS enables NTLM-hash leak / protocol-handler abuse.
// Same guard the renderer applies before making a link clickable (Markdown.tsx)
// and index.ts applies before every shell.openExternal. Exported so the wiring's
// real openExternal validates against the exact same list — no drift.
export const LINK_SCHEMES = ['http', 'https']

// Electron-touching actions the pure builder cannot perform itself. The wiring in
// contextMenu.ts injects real implementations (electron clipboard + the app's
// safe scheme-checked shell.openExternal); tests inject fakes and assert the
// click handlers call them with the exact link URL.
export type ContextMenuDeps = {
  /** Copy a string to the system clipboard. */
  copyText: (text: string) => void
  /** Open a URL in the user's default browser (scheme-validated). */
  openExternal: (url: string) => void
}

// Only the bits of ContextMenuParams this builder reads. Lets tests construct a
// params object without faking Electron's full (large) interface. `linkURL` is
// '' when the right-click was not on a hyperlink.
export type ContextMenuInput = Pick<
  ContextMenuParams,
  | 'isEditable'
  | 'selectionText'
  | 'editFlags'
  | 'misspelledWord'
  | 'dictionarySuggestions'
  | 'linkURL'
>

/**
 * The menu for a right-click, or [] when there is nothing useful to offer (a
 * right-click on a non-editable area with no selection and no link) — the caller
 * must not pop up an empty menu.
 *
 * When the right-click landed on an http/https hyperlink, a link group (Open Link,
 * Copy Link Address) is prepended ahead of any editing/selection items, matching
 * Chrome/Edge ordering. The link actions are electron-touching, so they are
 * injected via `deps`; without `deps` (or on a non-web link) the menu is exactly
 * the editing menu — behaviour is unchanged.
 */
export function buildContextMenuTemplate(
  params: ContextMenuInput,
  deps?: ContextMenuDeps
): MenuItemConstructorOptions[] {
  const editMenu = buildEditMenu(params)
  const linkGroup = buildLinkGroup(params.linkURL, deps)
  // No link → identical to the editing-only menu (unchanged behaviour). A single
  // separator joins the two groups only when both are non-empty, preserving the
  // "never leading/trailing/doubled separator" invariant.
  if (!linkGroup.length) return editMenu
  if (!editMenu.length) return linkGroup
  return [...linkGroup, { type: 'separator' }, ...editMenu]
}

/**
 * Link actions for a right-clicked hyperlink, or [] when there is no link, no
 * injected deps, or the href is not an http/https URL (a file://, UNC, or
 * custom-protocol link is dropped, not opened).
 */
function buildLinkGroup(
  linkURL: string | undefined,
  deps?: ContextMenuDeps
): MenuItemConstructorOptions[] {
  if (!deps || !linkURL || !isAllowedExternalScheme(linkURL, LINK_SCHEMES)) return []
  return [
    { label: 'Open Link', click: () => deps.openExternal(linkURL) },
    { label: 'Copy Link Address', click: () => deps.copyText(linkURL) }
  ]
}

/**
 * The editing/selection menu for the focused element. Items are role-based, so
 * Chromium performs the action against the focused webContents and greys out what
 * isn't currently possible. We still filter on editFlags rather than showing
 * everything disabled: a menu of five dead items is noise, and Windows apps
 * conventionally hide inapplicable edit commands.
 */
function buildEditMenu(params: ContextMenuInput): MenuItemConstructorOptions[] {
  const flags = params.editFlags
  const hasSelection = params.selectionText.trim().length > 0

  // Read-only surface (a message bubble, a transcript, a label). Copying the
  // selection is the only sensible action; Select All is offered so keyboard and
  // mouse users can grab the whole block.
  if (!params.isEditable) {
    if (!hasSelection || !flags.canCopy) return []
    const items: MenuItemConstructorOptions[] = [{ role: 'copy' }]
    if (flags.canSelectAll) items.push({ type: 'separator' }, { role: 'selectAll' })
    return items
  }

  // Editable field (chat composer, search box, settings input). Built as GROUPS,
  // with a separator inserted only between two non-empty ones — so no arrangement
  // of flags can produce a leading, trailing, or doubled divider.
  const items: MenuItemConstructorOptions[] = []
  const addGroup = (group: MenuItemConstructorOptions[]): void => {
    if (!group.length) return
    if (items.length) items.push({ type: 'separator' })
    items.push(...group)
  }

  // Spelling comes first, the way every Windows text field does it. This is not
  // optional polish: Electron enables spellcheck by DEFAULT, so the composer
  // already draws red squiggles — a menu without corrections would show the user
  // a misspelling it refuses to fix.
  const spelling: MenuItemConstructorOptions[] = []
  if (params.misspelledWord) {
    const word = params.misspelledWord
    for (const suggestion of params.dictionarySuggestions) {
      spelling.push({
        label: suggestion,
        click: (_item, win) => asBrowserWindow(win)?.webContents.replaceMisspelling(suggestion)
      })
    }
    // Say so explicitly rather than silently showing an editing menu on a word
    // Chromium has flagged — otherwise the squiggle looks like a bug.
    if (!spelling.length) spelling.push({ label: 'No spelling suggestions', enabled: false })
    spelling.push(
      { type: 'separator' },
      {
        label: 'Add to dictionary',
        click: (_item, win) =>
          asBrowserWindow(win)?.webContents.session.addWordToSpellCheckerDictionary(word)
      }
    )
  }
  addGroup(spelling)

  const history: MenuItemConstructorOptions[] = []
  if (flags.canUndo) history.push({ role: 'undo' })
  if (flags.canRedo) history.push({ role: 'redo' })
  addGroup(history)

  const edit: MenuItemConstructorOptions[] = []
  if (flags.canCut) edit.push({ role: 'cut' })
  if (flags.canCopy) edit.push({ role: 'copy' })
  if (flags.canPaste) edit.push({ role: 'paste' })
  // Delete belongs in this group on Windows (Notepad, Edge, and every Win32 edit
  // control offer it); it only means anything with a selection to delete.
  if (flags.canDelete && hasSelection) edit.push({ role: 'delete' })
  addGroup(edit)

  addGroup(flags.canSelectAll ? [{ role: 'selectAll' }] : [])

  return items
}
