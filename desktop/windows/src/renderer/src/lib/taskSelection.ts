// Multi-select model for the Tasks list (mac parity: TaskMultiSelection /
// TasksViewModel+MultiSelection). Pure functions over the FLAT rendered order —
// the page owns rendering; this owns what a click/keystroke does to the selected
// set so the rules are testable without a DOM.
//
// Semantics (standard list multi-select, matching the mac page):
// - plain click        → select only that row (anchor moves there)
// - ctrl/cmd click     → toggle that row, anchor moves there
// - shift click        → contiguous range from the anchor to the row, UNIONED
//                        into the selection (rows outside the range stay
//                        selected; the anchor stays put so shift-clicking
//                        around keeps pivoting on the same anchor)

export type TaskSelection = {
  /** Selected local row ids. */
  selected: ReadonlySet<number>
  /** Pivot row for shift-ranges; null until a first click. */
  anchor: number | null
}

export const EMPTY_SELECTION: TaskSelection = { selected: new Set(), anchor: null }

export type SelectionModifiers = { ctrl: boolean; shift: boolean }

function rangeBetween(order: readonly number[], a: number, b: number): number[] {
  const ai = order.indexOf(a)
  const bi = order.indexOf(b)
  if (ai === -1 || bi === -1) return bi === -1 ? [] : [b]
  const [lo, hi] = ai <= bi ? [ai, bi] : [bi, ai]
  return order.slice(lo, hi + 1)
}

export function applySelectionClick(
  order: readonly number[],
  current: TaskSelection,
  id: number,
  mods: SelectionModifiers
): TaskSelection {
  if (mods.shift && current.anchor != null) {
    const range = rangeBetween(order, current.anchor, id)
    const base = new Set(current.selected)
    for (const r of range) base.add(r)
    return { selected: base, anchor: current.anchor }
  }
  if (mods.ctrl) {
    const next = new Set(current.selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return { selected: next, anchor: id }
  }
  return { selected: new Set([id]), anchor: id }
}

/** Space-bar style toggle on the keyboard-focused row: same as a ctrl click. */
export function toggleInSelection(current: TaskSelection, id: number): TaskSelection {
  return applySelectionClick([], current, id, { ctrl: true, shift: false })
}

export function selectAll(order: readonly number[]): TaskSelection {
  // Anchor on the LAST rendered row, matching mac's selectAll (a follow-up
  // shift-click then ranges from the bottom of the list).
  return { selected: new Set(order), anchor: order.length > 0 ? order[order.length - 1] : null }
}

export function clearSelection(): TaskSelection {
  return { selected: new Set(), anchor: null }
}

/** Drop ids that no longer exist in the rendered order (rows completed away,
 *  deleted, or hidden by a filter change). Keeps the anchor only if it survives. */
export function pruneSelection(order: readonly number[], current: TaskSelection): TaskSelection {
  if (current.selected.size === 0 && current.anchor == null) return current
  const alive = new Set(order)
  const kept = new Set([...current.selected].filter((id) => alive.has(id)))
  const anchor = current.anchor != null && alive.has(current.anchor) ? current.anchor : null
  if (kept.size === current.selected.size && anchor === current.anchor) return current
  return { selected: kept, anchor }
}
