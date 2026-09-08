import { describe, it, expect } from 'vitest'
import {
  emptySourceState,
  filterNew,
  normalizeSourceState,
  recordProcessed,
  MAX_PROCESSED
} from './syncStateLogic'

describe('filterNew', () => {
  it('excludes items whose id is already processed', () => {
    const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
    expect(filterNew(items, ['b']).map((i) => i.id)).toEqual(['a', 'c'])
  })

  it('returns all when nothing processed', () => {
    expect(filterNew([{ id: 'a' }], []).map((i) => i.id)).toEqual(['a'])
  })
})

describe('normalizeSourceState', () => {
  it('returns an empty state for missing or malformed persisted data', () => {
    expect(normalizeSourceState(null)).toEqual(emptySourceState())
    expect(normalizeSourceState('bad')).toEqual(emptySourceState())
    expect(normalizeSourceState({ lastSyncAt: 'soon', processedIds: 'a,b' })).toEqual(
      emptySourceState()
    )
  })

  it('keeps valid fields and drops invalid processed ids', () => {
    expect(
      normalizeSourceState({
        lastSyncAt: 1234,
        processedIds: ['a', '', 42, 'b', 'a', 'c']
      })
    ).toEqual({ lastSyncAt: 1234, processedIds: ['b', 'a', 'c'] })
  })

  it('bounds normalized ids to the newest MAX_PROCESSED entries', () => {
    const ids = Array.from({ length: MAX_PROCESSED + 2 }, (_, i) => `id${i}`)
    const next = normalizeSourceState({ lastSyncAt: 1, processedIds: ids })
    expect(next.processedIds.length).toBe(MAX_PROCESSED)
    expect(next.processedIds[0]).toBe('id2')
    expect(next.processedIds.at(-1)).toBe(`id${MAX_PROCESSED + 1}`)
  })

  it('bounds normalized ids after deduping newest entries', () => {
    const ids = [...Array.from({ length: MAX_PROCESSED }, (_, i) => `id${i}`), 'tail', 'tail']
    const next = normalizeSourceState({ lastSyncAt: 1, processedIds: ids })
    expect(next.processedIds.length).toBe(MAX_PROCESSED)
    expect(next.processedIds[0]).toBe('id1')
    expect(next.processedIds.at(-1)).toBe('tail')
  })
})

describe('recordProcessed', () => {
  it('merges new ids, dedups, and advances lastSyncAt', () => {
    const next = recordProcessed({ lastSyncAt: 0, processedIds: ['a'] }, ['a', 'b'], 1234)
    expect(next.lastSyncAt).toBe(1234)
    expect(next.processedIds).toEqual(['a', 'b'])
  })

  it('bounds the processed set to the newest MAX_PROCESSED ids', () => {
    const start = emptySourceState()
    const ids = Array.from({ length: MAX_PROCESSED + 5 }, (_, i) => `id${i}`)
    const next = recordProcessed(start, ids, 1)
    expect(next.processedIds.length).toBe(MAX_PROCESSED)
    expect(next.processedIds[0]).toBe('id5') // oldest 5 dropped
    expect(next.processedIds.at(-1)).toBe(`id${MAX_PROCESSED + 4}`)
  })
})
