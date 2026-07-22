// Pure decision logic for the Conversations list's optimistic mutations (delete
// undo-window, merge). Extracted from Conversations.tsx so the fragile bits — which
// rows to hide, how to restore them on undo, whether a merge has landed server-side,
// and whether a late async load may still commit — are unit-testable without React.

import type { ConversationRow } from '../pageCache'

/** Remove every row whose id is in `ids`. The merged list is always sorted
 *  sortAt-desc, so filtering preserves that order. Pure. */
export function removeRows(rows: ConversationRow[], ids: Iterable<string>): ConversationRow[] {
  const set = ids instanceof Set ? ids : new Set(ids)
  if (set.size === 0) return rows
  return rows.filter((r) => !set.has(r.id))
}

/** Re-insert previously-removed rows (undo), restoring the list's sortAt-desc
 *  invariant. Rows already present are not duplicated. Pure. */
export function restoreRows(
  rows: ConversationRow[],
  removed: ConversationRow[]
): ConversationRow[] {
  if (removed.length === 0) return rows
  const present = new Set(rows.map((r) => r.id))
  const toAdd = removed.filter((r) => !present.has(r.id))
  if (toAdd.length === 0) return rows
  return [...rows, ...toAdd].sort((a, b) => b.sortAt - a.sortAt)
}

/** A merge has landed once NONE of the merged originals remain in a freshly-fetched
 *  set of cloud conversation ids (the backend deletes the originals asynchronously).
 *  Drives the merge poll's early-stop. Pure. */
export function mergeApplied(originalIds: Iterable<string>, cloudIds: Iterable<string>): boolean {
  const set = cloudIds instanceof Set ? cloudIds : new Set(cloudIds)
  for (const id of originalIds) if (set.has(id)) return false
  return true
}

/** A load/poll response may commit its result only if it is still the newest one
 *  issued. A superseded (stale) response must never overwrite fresher state — this
 *  is the epoch guard that prevents a slow 0s refetch from clobbering a 2.5s one. */
export function shouldCommit(gen: number, latest: number): boolean {
  return gen === latest
}
