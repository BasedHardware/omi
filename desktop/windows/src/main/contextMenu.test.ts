import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { BrowserWindow, ContextMenuParams } from 'electron'

type Item = { role?: string; type?: string }

const popup = vi.fn()
const buildFromTemplate = vi.fn((_template: Item[]) => ({ popup }))
vi.mock('electron', () => ({
  Menu: { buildFromTemplate: (t: Item[]) => buildFromTemplate(t) }
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

const roles = (): (string | undefined)[] => {
  const t = buildFromTemplate.mock.calls.at(-1)?.[0]
  if (!t) throw new Error('Menu.buildFromTemplate was never called')
  return t.map((i) => i.role ?? i.type)
}

describe('installContextMenu', () => {
  beforeEach(() => {
    popup.mockClear()
    buildFromTemplate.mockClear()
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
})
