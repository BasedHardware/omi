import { describe, it, expect, vi } from 'vitest'
import type { ContextMenuParams } from 'electron'
import {
  BAR_RESET_VOICE_LABEL,
  BAR_SNOOZE_LABEL,
  buildBarContextMenuTemplate,
  type BarContextMenuDeps
} from './barContextMenuTemplate'

// Pure-builder tests (no Electron runtime): the module has no electron VALUE
// import, so it imports cleanly under vitest. The wiring (barContextMenu.ts,
// which does import Menu/clipboard/shell) is exercised in the running app.

type Item = { role?: string; type?: string; label?: string; click?: (...a: unknown[]) => void }

const params = (p: Partial<ContextMenuParams> = {}): ContextMenuParams =>
  ({
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
  }) as ContextMenuParams

const deps = (over: Partial<BarContextMenuDeps> = {}): BarContextMenuDeps => ({
  copyText: vi.fn(),
  openExternal: vi.fn(),
  snooze: vi.fn(),
  resetVoicePlane: vi.fn(),
  ...over
})

const ids = (t: Item[]): (string | undefined)[] => t.map((i) => i.role ?? i.type ?? i.label)

describe('buildBarContextMenuTemplate', () => {
  it('offers the snooze + Reset voice on a right-click over empty bar chrome', () => {
    const t = buildBarContextMenuTemplate(params(), deps()) as Item[]
    expect(ids(t)).toEqual([BAR_SNOOZE_LABEL, BAR_RESET_VOICE_LABEL])
  })

  it('runs the injected resetVoicePlane when Reset voice is clicked', () => {
    const d = deps()
    const t = buildBarContextMenuTemplate(params(), d) as Item[]
    t.find((i) => i.label === BAR_RESET_VOICE_LABEL)?.click?.()
    expect(d.resetVoicePlane).toHaveBeenCalledTimes(1)
    expect(d.snooze).not.toHaveBeenCalled()
  })

  it('runs the injected snooze when the snooze item is clicked', () => {
    const d = deps()
    const t = buildBarContextMenuTemplate(params(), d) as Item[]
    t.find((i) => i.label === BAR_SNOOZE_LABEL)?.click?.()
    expect(d.snooze).toHaveBeenCalledTimes(1)
  })

  it('appends the snooze after the editing menu (own separator) on a text selection', () => {
    const t = buildBarContextMenuTemplate(
      params({
        isEditable: true,
        selectionText: 'hi',
        editFlags: {
          canUndo: false,
          canRedo: false,
          canCut: true,
          canCopy: true,
          canPaste: true,
          canDelete: true,
          canSelectAll: true,
          canEditRichly: true
        } as ContextMenuParams['editFlags']
      }),
      deps()
    ) as Item[]
    expect(ids(t)).toEqual([
      'cut',
      'copy',
      'paste',
      'delete',
      'separator',
      'selectAll',
      'separator',
      BAR_SNOOZE_LABEL,
      BAR_RESET_VOICE_LABEL
    ])
  })

  it('appends the snooze after a link menu on a right-clicked http/https link', () => {
    const t = buildBarContextMenuTemplate(params({ linkURL: 'https://omi.me/x' }), deps()) as Item[]
    expect(ids(t)).toEqual([
      'Open Link',
      'Copy Link Address',
      'separator',
      BAR_SNOOZE_LABEL,
      BAR_RESET_VOICE_LABEL
    ])
  })
})
