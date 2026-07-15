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

// Defaults to "no misspelling"; spell-check cases opt in.
const input = (over: Partial<ContextMenuInput> = {}): ContextMenuInput => ({
  isEditable: false,
  selectionText: '',
  editFlags: flags(),
  misspelledWord: '',
  dictionarySuggestions: [],
  ...over
})

const build = (over: Partial<ContextMenuInput> = {}): ReturnType<typeof buildContextMenuTemplate> =>
  buildContextMenuTemplate(input(over))

// A menu item is identified by its role, its separator-ness, or its label (the
// spelling suggestions are labels, not roles).
const ids = (t: ReturnType<typeof buildContextMenuTemplate>): (string | undefined)[] =>
  t.map((i) => i.role ?? i.type ?? i.label)

const ALL_EDIT = flags({
  canUndo: true,
  canRedo: true,
  canCut: true,
  canCopy: true,
  canPaste: true,
  canDelete: true,
  canSelectAll: true
})

describe('buildContextMenuTemplate', () => {
  it('offers nothing on a read-only area with no selection (caller must not popup)', () => {
    expect(build()).toEqual([])
  })

  it('treats a whitespace-only selection as no selection', () => {
    expect(build({ selectionText: '   \n ', editFlags: flags({ canCopy: true }) })).toEqual([])
  })

  it('offers copy (+ select all) on selected read-only text', () => {
    const t = build({
      selectionText: 'hello',
      editFlags: flags({ canCopy: true, canSelectAll: true })
    })
    expect(ids(t)).toEqual(['copy', 'separator', 'selectAll'])
  })

  it('offers nothing on read-only text that cannot be copied', () => {
    // The file's own rule is "filter on editFlags", and the read-only branch used
    // to ignore canCopy — the one place the policy was broken.
    expect(build({ selectionText: 'hello', editFlags: flags({ canCopy: false }) })).toEqual([])
  })

  it('offers the full edit set in an editable field, Delete included', () => {
    const t = build({ isEditable: true, selectionText: 'sel', editFlags: ALL_EDIT })
    expect(ids(t)).toEqual([
      'undo',
      'redo',
      'separator',
      'cut',
      'copy',
      'paste',
      'delete',
      'separator',
      'selectAll'
    ])
  })

  it('omits Delete when there is nothing selected to delete', () => {
    const t = build({ isEditable: true, selectionText: '', editFlags: ALL_EDIT })
    expect(ids(t)).not.toContain('delete')
  })

  it('hides inapplicable commands rather than showing them disabled', () => {
    // Empty composer, clipboard has content: paste + select all only.
    const t = build({
      isEditable: true,
      editFlags: flags({ canPaste: true, canSelectAll: true })
    })
    expect(ids(t)).toEqual(['paste', 'separator', 'selectAll'])
  })

  it('offers spelling suggestions FIRST on a misspelled word, plus Add to dictionary', () => {
    // Electron enables spellcheck by default, so the composer already draws red
    // squiggles. A menu with no corrections would show a misspelling it refuses
    // to fix.
    const t = build({
      isEditable: true,
      misspelledWord: 'teh',
      dictionarySuggestions: ['the', 'ten'],
      editFlags: flags({ canPaste: true, canSelectAll: true })
    })
    expect(ids(t)).toEqual([
      'the',
      'ten',
      'separator',
      'Add to dictionary',
      'separator',
      'paste',
      'separator',
      'selectAll'
    ])
  })

  it('says so explicitly when a misspelled word has no suggestions', () => {
    const t = build({ isEditable: true, misspelledWord: 'zzxq', dictionarySuggestions: [] })
    expect(ids(t)).toEqual(['No spelling suggestions', 'separator', 'Add to dictionary'])
    expect(t[0].enabled).toBe(false)
  })

  it('never starts or ends with a separator, and never emits adjacent separators', () => {
    // Exhaustive sweep: a stray divider is THE classic bug in conditionally
    // assembled menus. Varies isEditable, all six flags the builder reads, and
    // whether a misspelling with/without suggestions is present — 2 * 2^6 * 3 = 384
    // combinations. The spelling group made this materially more likely to break:
    // it is emitted BEFORE the rest and can be the only group present.
    const bools = [false, true]
    const spellings = [
      { misspelledWord: '', dictionarySuggestions: [] as string[] },
      { misspelledWord: 'teh', dictionarySuggestions: ['the'] },
      { misspelledWord: 'zzxq', dictionarySuggestions: [] as string[] }
    ]
    let checked = 0
    for (const isEditable of bools)
      for (const canUndo of bools)
        for (const canRedo of bools)
          for (const canCut of bools)
            for (const canCopy of bools)
              for (const canPaste of bools)
                for (const canSelectAll of bools)
                  for (const spelling of spellings) {
                    const t = build({
                      isEditable,
                      selectionText: 'sel',
                      editFlags: flags({
                        canUndo,
                        canRedo,
                        canCut,
                        canCopy,
                        canPaste,
                        canSelectAll,
                        canDelete: true
                      }),
                      ...spelling
                    })
                    checked++
                    if (!t.length) continue
                    const r = ids(t)
                    expect(r[0]).not.toBe('separator')
                    expect(r[r.length - 1]).not.toBe('separator')
                    for (let i = 1; i < r.length; i++) {
                      expect(r[i] === 'separator' && r[i - 1] === 'separator').toBe(false)
                    }
                  }
    expect(checked).toBe(384)
  })
})
