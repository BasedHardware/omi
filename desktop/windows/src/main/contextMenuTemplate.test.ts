import { describe, it, expect } from 'vitest'
import { buildContextMenuTemplate } from './contextMenuTemplate'
import type { ContextMenuInput } from './contextMenuTemplate'

type Flags = ContextMenuInput['editFlags']

const flags = (over: Partial<Flags> = {}): Flags => ({
  canUndo: false,
  canRedo: false,
  canCut: false,
  canCopy: false,
  canPaste: false,
  canDelete: false,
  canSelectAll: false,
  canEditRichly: false,
  ...over
})

const roles = (t: ReturnType<typeof buildContextMenuTemplate>): (string | undefined)[] =>
  t.map((i) => i.role ?? i.type)

describe('buildContextMenuTemplate', () => {
  it('offers nothing on a read-only area with no selection (caller must not popup)', () => {
    expect(
      buildContextMenuTemplate({ isEditable: false, selectionText: '', editFlags: flags() })
    ).toEqual([])
  })

  it('treats whitespace-only selection as no selection', () => {
    expect(
      buildContextMenuTemplate({
        isEditable: false,
        selectionText: '   \n ',
        editFlags: flags({ canCopy: true })
      })
    ).toEqual([])
  })

  it('offers copy (+ select all) on selected read-only text', () => {
    const t = buildContextMenuTemplate({
      isEditable: false,
      selectionText: 'hello',
      editFlags: flags({ canCopy: true, canSelectAll: true })
    })
    expect(roles(t)).toEqual(['copy', 'separator', 'selectAll'])
  })

  it('offers the full edit set in an editable field', () => {
    const t = buildContextMenuTemplate({
      isEditable: true,
      selectionText: 'sel',
      editFlags: flags({
        canUndo: true,
        canRedo: true,
        canCut: true,
        canCopy: true,
        canPaste: true,
        canSelectAll: true
      })
    })
    expect(roles(t)).toEqual([
      'undo',
      'redo',
      'separator',
      'cut',
      'copy',
      'paste',
      'separator',
      'selectAll'
    ])
  })

  it('hides inapplicable commands rather than showing them disabled', () => {
    // Empty composer, clipboard has content: paste + select all only. No cut/copy
    // (nothing selected), no undo/redo (nothing typed yet).
    const t = buildContextMenuTemplate({
      isEditable: true,
      selectionText: '',
      editFlags: flags({ canPaste: true, canSelectAll: true })
    })
    expect(roles(t)).toEqual(['paste', 'separator', 'selectAll'])
  })

  it('never starts or ends with a separator, and never emits adjacent separators', () => {
    // Exhaustive sweep of every editFlags combination that varies the menu, in
    // both editable and read-only modes: a stray separator is the classic bug in
    // conditionally-assembled menus, and it shows up as a floating divider line.
    const bools = [false, true]
    for (const isEditable of bools) {
      for (const canUndo of bools)
        for (const canRedo of bools)
          for (const canCut of bools)
            for (const canCopy of bools)
              for (const canPaste of bools)
                for (const canSelectAll of bools) {
                  const t = buildContextMenuTemplate({
                    isEditable,
                    selectionText: 'sel',
                    editFlags: flags({
                      canUndo,
                      canRedo,
                      canCut,
                      canCopy,
                      canPaste,
                      canSelectAll
                    })
                  })
                  if (!t.length) continue
                  const r = roles(t)
                  expect(r[0]).not.toBe('separator')
                  expect(r[r.length - 1]).not.toBe('separator')
                  for (let i = 1; i < r.length; i++) {
                    expect(r[i] === 'separator' && r[i - 1] === 'separator').toBe(false)
                  }
                }
    }
  })
})
