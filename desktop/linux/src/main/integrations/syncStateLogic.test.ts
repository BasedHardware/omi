import { describe, it, expect } from 'vitest'
import {
  emptySourceState,
  filterNew,
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
