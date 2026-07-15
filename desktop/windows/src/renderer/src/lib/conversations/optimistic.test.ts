import { describe, it, expect } from 'vitest'
import { removeRows, restoreRows, mergeApplied, shouldCommit } from './optimistic'
import type { ConversationRow } from '../pageCache'

function row(id: string, sortAt: number, source: 'cloud' | 'local' = 'cloud'): ConversationRow {
  return { id, title: id, subtitle: '', preview: '', source, sortAt }
}

describe('removeRows / restoreRows (delete undo window)', () => {
  const rows = [row('c', 300), row('b', 200), row('a', 100)] // sortAt-desc

  it('removes the targeted ids (M1: deleted cloud row must disappear immediately)', () => {
    const after = removeRows(rows, ['b'])
    expect(after.map((r) => r.id)).toEqual(['c', 'a'])
  })

  it('accepts a Set and an array interchangeably', () => {
    expect(removeRows(rows, new Set(['c', 'a'])).map((r) => r.id)).toEqual(['b'])
  })

  it('is a no-op for an empty id set (returns same reference)', () => {
    expect(removeRows(rows, [])).toBe(rows)
  })

  it('undo restores removed rows in the correct sortAt-desc position', () => {
    const removed = [row('b', 200)]
    const after = removeRows(rows, ['b'])
    const restored = restoreRows(after, removed)
    expect(restored.map((r) => r.id)).toEqual(['c', 'b', 'a'])
  })

  it('undo does not duplicate a row that is already present', () => {
    const restored = restoreRows(rows, [row('b', 200)])
    expect(restored.map((r) => r.id)).toEqual(['c', 'b', 'a'])
  })
})

describe('mergeApplied (merge poll early-stop)', () => {
  it('is false while any original still exists server-side', () => {
    expect(mergeApplied(['a', 'b'], new Set(['a', 'x', 'y']))).toBe(false)
  })

  it('is true once all originals are gone (merge landed)', () => {
    expect(mergeApplied(['a', 'b'], new Set(['merged', 'x']))).toBe(true)
  })

  it('the un-merged 0s fetch (originals still present) does NOT count as applied', () => {
    // M2: the immediate refetch returns the originals — the poll must keep going.
    expect(mergeApplied(['a', 'b'], new Set(['a', 'b']))).toBe(false)
  })
})

describe('shouldCommit (stale-response epoch guard)', () => {
  it('lets the newest load commit', () => {
    expect(shouldCommit(2, 2)).toBe(true)
  })

  it('drops a superseded (stale) load so it cannot clobber fresher state', () => {
    // M2: a slow 0s refetch (gen 1) resolving after the 2.5s one (gen 2) must lose.
    expect(shouldCommit(1, 2)).toBe(false)
  })
})
