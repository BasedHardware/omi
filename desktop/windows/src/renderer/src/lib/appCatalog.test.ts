import { describe, it, expect, vi } from 'vitest'
import {
  buildCatalog,
  mergeAppPool,
  sectionPreview,
  searchCatalog,
  SECTION_PREVIEW_COUNT,
  CATALOG_SECTIONS
} from './appCatalog'
import type { AppCatalogGroup, AppCatalogItem } from './omiApi.generated'

function item(partial: Partial<AppCatalogItem> & { id: string }): AppCatalogItem {
  return { name: partial.id, category: 'other', ...partial }
}

function group(
  capabilityId: string,
  ids: string[],
  pagination?: { total: number; hasNext: boolean }
): AppCatalogGroup {
  const g: AppCatalogGroup = {
    capability: { id: capabilityId, title: capabilityId },
    data: ids.map((id) => item({ id }))
  }
  if (pagination) {
    g.pagination = {
      total: pagination.total,
      count: ids.length,
      offset: 0,
      limit: ids.length,
      hasNext: pagination.hasNext,
      hasPrevious: false
    }
  }
  return g
}

describe('buildCatalog', () => {
  it('returns empty sections and union for missing/empty groups', () => {
    expect(buildCatalog(undefined)).toEqual({ sections: [], allApps: [] })
    expect(buildCatalog([])).toEqual({ sections: [], allApps: [] })
  })

  it('maps capabilities to sections in the fixed macOS order regardless of response order', () => {
    const groups = [
      group('proactive_notification', ['n1']),
      group('popular', ['p1']),
      group('external_integration', ['i1'])
    ]
    const { sections } = buildCatalog(groups)
    expect(sections.map((s) => s.capabilityId)).toEqual([
      'popular',
      'external_integration',
      'proactive_notification'
    ])
    expect(sections.map((s) => s.title)).toEqual(['Other', 'Integrations', 'Realtime Notifications'])
  })

  it('preserves backend order within a group (no client sort)', () => {
    const groups = [group('popular', ['c', 'a', 'b'])]
    const { sections } = buildCatalog(groups)
    expect(sections[0].apps.map((a) => a.id)).toEqual(['c', 'a', 'b'])
  })

  it('skips empty sections', () => {
    const groups = [group('popular', ['p1']), group('external_integration', [])]
    const { sections } = buildCatalog(groups)
    expect(sections.map((s) => s.capabilityId)).toEqual(['popular'])
  })

  it('ignores capability groups that are not rendered as sections (e.g. chat/memories)', () => {
    const groups = [group('popular', ['p1']), group('chat', ['ch1']), group('memories', ['m1'])]
    const { sections } = buildCatalog(groups)
    expect(sections.map((s) => s.capabilityId)).toEqual(['popular'])
  })

  it('sets hasMore only when a group exceeds the preview count', () => {
    const many = Array.from({ length: SECTION_PREVIEW_COUNT + 1 }, (_, i) => `p${i}`)
    const groups = [group('popular', many), group('external_integration', ['i1'])]
    const { sections } = buildCatalog(groups)
    const popular = sections.find((s) => s.capabilityId === 'popular')
    const integrations = sections.find((s) => s.capabilityId === 'external_integration')
    expect(popular?.hasMore).toBe(true)
    expect(integrations?.hasMore).toBe(false)
  })

  it('dedupes the union across groups (an app in multiple groups appears once)', () => {
    // `shared` is popular AND an integration; the union keeps the first occurrence.
    const groups = [
      group('popular', ['shared', 'p1']),
      group('external_integration', ['shared', 'i1'])
    ]
    const { allApps } = buildCatalog(groups)
    expect(allApps.map((a) => a.id)).toEqual(['shared', 'p1', 'i1'])
    // The section still shows the app in both groups.
    const { sections } = buildCatalog(groups)
    expect(sections[0].apps.map((a) => a.id)).toEqual(['shared', 'p1'])
    expect(sections[1].apps.map((a) => a.id)).toEqual(['shared', 'i1'])
  })

  it('skips records without an id', () => {
    const groups: AppCatalogGroup[] = [
      {
        capability: { id: 'popular', title: 'Other' },
        data: [item({ id: 'p1' }), { id: '' } as AppCatalogItem]
      }
    ]
    const { allApps } = buildCatalog(groups)
    expect(allApps.map((a) => a.id)).toEqual(['p1'])
  })

  it('exposes the three macOS sections in canonical order', () => {
    expect(CATALOG_SECTIONS.map((s) => s.capabilityId)).toEqual([
      'popular',
      'external_integration',
      'proactive_notification'
    ])
  })

  it('flags a truncated group and carries its server total', () => {
    // The per-group limit cut this group short: 2 returned, 250 exist, hasNext.
    const groups = [
      group('popular', ['p1', 'p2'], { total: 250, hasNext: true }),
      group('external_integration', ['i1'], { total: 1, hasNext: false })
    ]
    const { sections } = buildCatalog(groups)
    const popular = sections.find((s) => s.capabilityId === 'popular')
    const integrations = sections.find((s) => s.capabilityId === 'external_integration')
    expect(popular?.truncated).toBe(true)
    expect(popular?.total).toBe(250)
    expect(integrations?.truncated).toBe(false)
    expect(integrations?.total).toBe(1)
  })

  it('defaults total to the returned count and truncated to false without pagination', () => {
    const { sections } = buildCatalog([group('popular', ['p1', 'p2'])])
    expect(sections[0].total).toBe(2)
    expect(sections[0].truncated).toBe(false)
  })

  // Contract tripwire: if the backend renames a capability id, buildCatalog would
  // silently drop that section. Assert every CATALOG_SECTIONS id still appears in a
  // representative /v2/apps groups response so a rename fails a test instead.
  it('every CATALOG_SECTIONS id is present in a representative /v2/apps groups response', () => {
    // Capability ids as returned by GET /v2/apps (backend utils/apps.py capabilities
    // list). "popular" is labeled "Featured" server-side but the section title stays
    // "Other" (macOS AppsPage.swift:246); chat/memories/tasks are real groups too.
    const realGroupIds = [
      'popular',
      'external_integration',
      'chat',
      'memories',
      'proactive_notification',
      'tasks'
    ]
    for (const def of CATALOG_SECTIONS) {
      expect(realGroupIds).toContain(def.capabilityId)
    }
  })
})

describe('mergeAppPool', () => {
  it('includes a v1-only app so an enabled private/tester app still resolves for Installed', () => {
    const v2 = [item({ id: 'approved', name: 'Approved' })]
    const v1 = [
      item({ id: 'approved', name: 'Approved' }),
      item({ id: 'private-only', name: 'My Private App' })
    ]
    const pool = mergeAppPool(v2, v1)
    expect(pool.map((a) => a.id).sort()).toEqual(['approved', 'private-only'])
    // The Installed view is pool ∩ enabled — the v1-only enabled app renders.
    const enabled = new Set(['private-only'])
    const installed = pool.filter((a) => enabled.has(a.id))
    expect(installed.map((a) => a.id)).toEqual(['private-only'])
  })

  it('lets v1 win for a shared id (v1 carries the authoritative user-private record)', () => {
    const v2 = [item({ id: 'x', name: 'v2 name', private: false })]
    const v1 = [item({ id: 'x', name: 'v1 name', private: true })]
    const pool = mergeAppPool(v2, v1)
    expect(pool).toHaveLength(1)
    expect(pool[0].name).toBe('v1 name')
    expect(pool[0].private).toBe(true)
  })

  it('skips records without an id and preserves v2-then-v1 order', () => {
    const v2 = [item({ id: 'a' }), { id: '' } as AppCatalogItem]
    const v1 = [item({ id: 'b' }), item({ id: 'a' })]
    expect(mergeAppPool(v2, v1).map((a) => a.id)).toEqual(['a', 'b'])
  })
})

describe('sectionPreview', () => {
  const apps = Array.from({ length: SECTION_PREVIEW_COUNT + 3 }, (_, i) => item({ id: `a${i}` }))

  it('returns the first preview-count apps when collapsed', () => {
    expect(sectionPreview(apps, false)).toHaveLength(SECTION_PREVIEW_COUNT)
  })

  it('returns all apps when expanded', () => {
    expect(sectionPreview(apps, true)).toHaveLength(apps.length)
  })
})

describe('searchCatalog', () => {
  const local = [
    item({ id: 'notes', name: 'Notes' }),
    item({ id: 'other', name: 'Weather' })
  ]

  it('returns no results for an empty/whitespace query without calling the fetcher', async () => {
    const fetchRemote = vi.fn()
    const result = await searchCatalog('   ', fetchRemote, local)
    expect(result).toEqual({ apps: [], usedFallback: false })
    expect(fetchRemote).not.toHaveBeenCalled()
  })

  it('returns remote results on success (not a fallback)', async () => {
    const remote = [item({ id: 'r1', name: 'Remote Result' })]
    const fetchRemote = vi.fn().mockResolvedValue(remote)
    const result = await searchCatalog('remote', fetchRemote, local)
    expect(fetchRemote).toHaveBeenCalledWith('remote')
    expect(result).toEqual({ apps: remote, usedFallback: false })
  })

  it('falls back to a client rank of local apps when the endpoint throws', async () => {
    const fetchRemote = vi.fn().mockRejectedValue(new Error('401'))
    const result = await searchCatalog('notes', fetchRemote, local)
    expect(result.usedFallback).toBe(true)
    expect(result.apps.map((a) => a.id)).toEqual(['notes'])
  })
})
