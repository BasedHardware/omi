import { describe, it, expect } from 'vitest'
import {
  EMPTY_SELECTION,
  applySelectionClick,
  clearSelection,
  pruneSelection,
  selectAll,
  toggleInSelection
} from './taskSelection'

const order = [10, 20, 30, 40, 50]

describe('applySelectionClick', () => {
  it('plain click selects only the clicked row and moves the anchor', () => {
    const s1 = applySelectionClick(order, EMPTY_SELECTION, 30, { ctrl: false, shift: false })
    expect([...s1.selected]).toEqual([30])
    expect(s1.anchor).toBe(30)
    const s2 = applySelectionClick(order, s1, 50, { ctrl: false, shift: false })
    expect([...s2.selected]).toEqual([50])
    expect(s2.anchor).toBe(50)
  })

  it('ctrl click toggles membership and moves the anchor', () => {
    const s1 = applySelectionClick(order, EMPTY_SELECTION, 20, { ctrl: true, shift: false })
    const s2 = applySelectionClick(order, s1, 40, { ctrl: true, shift: false })
    expect(new Set(s2.selected)).toEqual(new Set([20, 40]))
    expect(s2.anchor).toBe(40)
    const s3 = applySelectionClick(order, s2, 20, { ctrl: true, shift: false })
    expect(new Set(s3.selected)).toEqual(new Set([40]))
    expect(s3.anchor).toBeNull()
  })

  it('shift click unions the contiguous range from the anchor into the selection', () => {
    const s1 = applySelectionClick(order, EMPTY_SELECTION, 20, { ctrl: false, shift: false })
    const s2 = applySelectionClick(order, s1, 40, { ctrl: false, shift: true })
    expect([...s2.selected].sort((a, b) => a - b)).toEqual([20, 30, 40])
    expect(s2.anchor).toBe(20)
    // Pivot the other way off the same anchor: rows outside the new range stay selected.
    const s3 = applySelectionClick(order, s2, 10, { ctrl: false, shift: true })
    expect([...s3.selected].sort((a, b) => a - b)).toEqual([10, 20, 30, 40])
    expect(s3.anchor).toBe(20)
  })

  it('shift range never clears rows selected outside the range', () => {
    const s1 = applySelectionClick(order, EMPTY_SELECTION, 50, { ctrl: true, shift: false }) // +50
    const s2 = applySelectionClick(order, s1, 10, { ctrl: true, shift: false }) // +10, anchor 10
    const s3 = applySelectionClick(order, s2, 30, { ctrl: false, shift: true }) // range 10-30
    expect([...s3.selected].sort((a, b) => a - b)).toEqual([10, 20, 30, 50])
  })

  it('shift click with no anchor behaves like a plain click', () => {
    const s = applySelectionClick(order, EMPTY_SELECTION, 30, { ctrl: false, shift: true })
    expect([...s.selected]).toEqual([30])
    expect(s.anchor).toBe(30)
  })

  it('a shift range to a row missing from the order resolves to no new rows', () => {
    const s1 = applySelectionClick(order, EMPTY_SELECTION, 20, { ctrl: false, shift: false })
    const s2 = applySelectionClick(order, s1, 999, { ctrl: false, shift: true })
    // The union base keeps the anchor's own selection; the empty range adds nothing.
    expect([...s2.selected]).toEqual([20])
  })
})

describe('helpers', () => {
  it('toggleInSelection is a ctrl-click', () => {
    const s = toggleInSelection(EMPTY_SELECTION, 30)
    expect([...s.selected]).toEqual([30])
    expect([...toggleInSelection(s, 30).selected]).toEqual([])
  })

  it('selectAll selects the whole order and anchors on the LAST row (mac)', () => {
    const s = selectAll(order)
    expect(new Set(s.selected)).toEqual(new Set(order))
    expect(s.anchor).toBe(50)
    expect(selectAll([]).anchor).toBeNull()
  })

  it('clearSelection empties everything', () => {
    const s = clearSelection()
    expect(s.selected.size).toBe(0)
    expect(s.anchor).toBeNull()
  })

  it('pruneSelection drops rows that left the rendered order', () => {
    const s1 = selectAll(order) // anchor 50 (last row)
    const pruned = pruneSelection([10, 30], s1)
    expect(new Set(pruned.selected)).toEqual(new Set([10, 30]))
    // The anchor (50) left the order too, so it clears.
    expect(pruned.anchor).toBeNull()
    const anchorKept = pruneSelection([10, 30], { selected: new Set([10, 30]), anchor: 10 })
    expect(anchorKept.anchor).toBe(10)
    const anchorGone = pruneSelection([30], { selected: new Set([30]), anchor: 10 })
    expect(anchorGone.anchor).toBeNull()
  })

  it('pruneSelection returns the same object when nothing changed', () => {
    const s = selectAll(order)
    expect(pruneSelection(order, s)).toBe(s)
  })
})
