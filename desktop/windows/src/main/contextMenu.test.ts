import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { BrowserWindow, ContextMenuParams } from 'electron'

type Item = { role?: string; type?: string; label?: string; click?: (...args: unknown[]) => void }

const popup = vi.fn()
const buildFromTemplate = vi.fn((_template: Item[]) => ({ popup }))
const writeText = vi.fn()
const openExternal = vi.fn()
vi.mock('electron', () => ({
  Menu: { buildFromTemplate: (t: Item[]) => buildFromTemplate(t) },
  clipboard: { writeText: (s: string) => writeText(s) },
  shell: { openExternal: (u: string) => openExternal(u) }
}))

const { installContextMenu } = await import('./contextMenu')

type Handler = (e: unknown, p: ContextMenuParams) => void

/** A window that just records the 'context-menu' handler installed on it. */
function fakeWindow(): { win: BrowserWindow; fire: (p: Partial<ContextMenuParams>) => void } {
  let handler: Handler | undefined
  const win = {
    webContents: {
      on: (event: string, cb: Handler) => {
        if (event === 'context-menu') handler = cb
      }
    }
  } as unknown as BrowserWindow

  const fire = (p: Partial<ContextMenuParams>): void => {
    if (!handler) throw new Error('no context-menu handler installed')
    handler({}, {
      isEditable: false,
      selectionText: '',
      linkURL: '',
      misspelledWord: '',
      dictionarySuggestions: [],
      editFlags: {
        canUndo: false,
        canRedo: false,
        canCut: false,
        canCopy: false,
        canPaste: false,
        canDelete: false,
        canSelectAll: false,
        canEditRichly: false
      },
      ...p
    } as ContextMenuParams)
  }
  return { win, fire }
}

const lastTemplate = (): Item[] => {
  const t = buildFromTemplate.mock.calls.at(-1)?.[0]
  if (!t) throw new Error('Menu.buildFromTemplate was never called')
  return t
}

const roles = (): (string | undefined)[] => lastTemplate().map((i) => i.role ?? i.type)
const ids = (): (string | undefined)[] => lastTemplate().map((i) => i.role ?? i.type ?? i.label)

describe('installContextMenu', () => {
  beforeEach(() => {
    popup.mockClear()
    buildFromTemplate.mockClear()
    writeText.mockClear()
    openExternal.mockClear()
  })

  it('pops a native menu over the owning window on a right-click in a text field', () => {
    const { win, fire } = fakeWindow()
    installContextMenu(win)

    fire({
      isEditable: true,
      selectionText: 'hi',
      editFlags: {
        canUndo: true,
        canRedo: false,
        canCut: true,
        canCopy: true,
        canPaste: true,
        canDelete: true,
        canSelectAll: true,
        canEditRichly: true
      } as ContextMenuParams['editFlags']
    })

    expect(buildFromTemplate).toHaveBeenCalledTimes(1)
    expect(roles()).toEqual([
      'undo',
      'separator',
      'cut',
      'copy',
      'paste',
      'delete',
      'separator',
      'selectAll'
    ])
    // Must be popped OVER the window it came from — a menu with no owner window
    // can appear on the wrong monitor and won't dismiss with the window.
    expect(popup).toHaveBeenCalledWith({ window: win })
  })

  it('pops NOTHING when there is nothing to offer (never show an empty menu)', () => {
    const { win, fire } = fakeWindow()
    installContextMenu(win)

    fire({ isEditable: false, selectionText: '' }) // read-only, no selection

    expect(buildFromTemplate).not.toHaveBeenCalled()
    expect(popup).not.toHaveBeenCalled()
  })

  it('offers Open Link / Copy Link Address on a right-clicked http/https link and wires them to electron', () => {
    const { win, fire } = fakeWindow()
    installContextMenu(win)

    fire({ linkURL: 'https://omi.me/x' })

    expect(ids()).toEqual(['Open Link', 'Copy Link Address'])
    const t = lastTemplate()
    // "Open Link" hands the URL to the OS browser via the scheme-checked opener.
    t.find((i) => i.label === 'Open Link')?.click?.()
    expect(openExternal).toHaveBeenCalledWith('https://omi.me/x')
    // "Copy Link Address" copies the raw href to the clipboard.
    t.find((i) => i.label === 'Copy Link Address')?.click?.()
    expect(writeText).toHaveBeenCalledWith('https://omi.me/x')
    expect(popup).toHaveBeenCalledWith({ window: win })
  })

  it('shows no link menu and never opens the OS for a non-web link (file://)', () => {
    const { win, fire } = fakeWindow()
    installContextMenu(win)

    fire({ linkURL: 'file:///etc/passwd' }) // read-only, no selection, disallowed scheme

    expect(buildFromTemplate).not.toHaveBeenCalled()
    expect(openExternal).not.toHaveBeenCalled()
  })
})
