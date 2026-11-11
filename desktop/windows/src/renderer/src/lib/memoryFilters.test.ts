import { describe, it, expect } from 'vitest'
import type { Memory } from '../hooks/useMemories'
import {
  categoryOf,
  filterMemories,
  formatMemoryDate,
  isNewMemory,
  isProtectedContent,
  layerLabel,
  NEW_MEMORY_WINDOW_MS,
  type MemoryCategory,
  type MemoryFilters
} from './memoryFilters'

function mem(over: Partial<Memory>): Memory {
  return {
    id: over.id ?? 'x',
    uid: 'u',
    content: over.content ?? 'content',
    created_at: over.created_at ?? '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over
  }
}

const baseFilters = (over: Partial<MemoryFilters> = {}): MemoryFilters => ({
  search: '',
  categories: new Set<MemoryCategory>(),
  layer: 'default',
  thisDeviceOnly: false,
  ...over
})

describe('categoryOf', () => {
  it('passes through the four known categories', () => {
    expect(categoryOf(mem({ category: 'manual' }))).toBe('manual')
    expect(categoryOf(mem({ category: 'system' }))).toBe('system')
    expect(categoryOf(mem({ category: 'interesting' }))).toBe('interesting')
    expect(categoryOf(mem({ category: 'workflow' }))).toBe('workflow')
  })
  it('folds unknown/absent categories to interesting', () => {
    expect(categoryOf(mem({ category: 'core' }))).toBe('interesting')
    expect(categoryOf(mem({}))).toBe('interesting')
  })
})

describe('layerLabel', () => {
  it('labels tiered memories and omits untiered ones', () => {
    expect(layerLabel(mem({ layer: 'short_term' }))).toBe('Short-term')
    expect(layerLabel(mem({ layer: 'long_term' }))).toBe('Long-term')
    expect(layerLabel(mem({ layer: 'archive' }))).toBe('Archive')
    expect(layerLabel(mem({}))).toBeNull()
    expect(layerLabel(mem({ layer: null }))).toBeNull()
  })
})

describe('isNewMemory', () => {
  const now = Date.parse('2026-01-01T00:01:30Z')
  it('is true within the 60s window and false after', () => {
    expect(isNewMemory(mem({ created_at: '2026-01-01T00:01:00Z' }), now)).toBe(true) // 30s old
    expect(isNewMemory(mem({ created_at: '2026-01-01T00:00:00Z' }), now)).toBe(false) // 90s old
  })
  it('is false for future timestamps and unparseable dates', () => {
    expect(isNewMemory(mem({ created_at: '2026-01-01T00:02:00Z' }), now)).toBe(false)
    expect(isNewMemory(mem({ created_at: 'not-a-date' }), now)).toBe(false)
  })
  it('exposes the window length', () => {
    expect(NEW_MEMORY_WINDOW_MS).toBe(60_000)
  })
})

describe('formatMemoryDate', () => {
  const now = Date.parse('2026-01-04T14:15:00Z')
  it('shows a relative age plus an absolute stamp', () => {
    const out = formatMemoryDate('2026-01-04T11:15:00Z', now) // 3h ago
    expect(out.startsWith('3h ago · ')).toBe(true)
  })
  it('drops the relative half once older than a week', () => {
    const out = formatMemoryDate('2025-12-01T00:00:00Z', now)
    expect(out.includes('ago')).toBe(false)
    expect(out.length).toBeGreaterThan(0)
  })
  it('returns empty string for an unparseable date', () => {
    expect(formatMemoryDate('nope', now)).toBe('')
  })
})

describe('isProtectedContent', () => {
  it('detects protected/encrypted placeholders', () => {
    expect(isProtectedContent('[Protected memory]')).toBe(true)
    expect(isProtectedContent('  [Encrypted]')).toBe(true)
    expect(isProtectedContent('Likes espresso')).toBe(false)
  })
})

describe('filterMemories', () => {
  const list = [
    mem({ id: 'a', content: 'Loves hiking in Oregon', category: 'system', layer: 'short_term' }),
    mem({ id: 'b', content: 'Paul Graham on focus', category: 'interesting', layer: 'long_term' }),
    mem({ id: 'c', content: 'Deploy checklist', category: 'workflow', layer: 'archive' }),
    mem({ id: 'd', content: 'Buy milk', category: 'manual' })
  ]

  it('search matches content case-insensitively', () => {
    const r = filterMemories(list, baseFilters({ search: 'OREGON' }))
    expect(r.map((m) => m.id)).toEqual(['a'])
  })

  it('empty category set keeps all; a set is OR within it (layer=archive to include c)', () => {
    // With no category or layer filter, the default layer excludes the archived
    // 'c', leaving three.
    expect(filterMemories(list, baseFilters()).map((m) => m.id).sort()).toEqual(['a', 'b', 'd'])
    // Category is independent of layer: select manual+workflow, and widen the
    // layer so the archived workflow item ('c') is in scope.
    const r = filterMemories(
      list,
      baseFilters({ categories: new Set(['manual', 'workflow']), layer: 'archive' })
    )
    expect(r.map((m) => m.id)).toEqual(['c']) // 'd' is manual but not archived
  })

  it('default layer excludes archive; a named layer narrows to it', () => {
    // 'd' has no layer → not archive → kept by default; 'c' is archived → dropped.
    expect(filterMemories(list, baseFilters()).map((m) => m.id).sort()).toEqual(['a', 'b', 'd'])
    expect(filterMemories(list, baseFilters({ layer: 'archive' })).map((m) => m.id)).toEqual(['c'])
    expect(filterMemories(list, baseFilters({ layer: 'short_term' })).map((m) => m.id)).toEqual([
      'a'
    ])
  })

  it('this-device filter matches primary or secondary capture devices', () => {
    const devList = [
      mem({ id: 'p', primary_capture_device: 'win-1' }),
      mem({ id: 's', capture_device_ids: ['win-1', 'mac-9'] }),
      mem({ id: 'o', primary_capture_device: 'mac-9' })
    ]
    const r = filterMemories(
      devList,
      baseFilters({ thisDeviceOnly: true, thisDeviceId: 'win-1' })
    )
    expect(r.map((m) => m.id).sort()).toEqual(['p', 's'])
  })
})
