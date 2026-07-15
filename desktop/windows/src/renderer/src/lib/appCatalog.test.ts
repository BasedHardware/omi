import { describe, it, expect, vi } from 'vitest'
import {
  buildCatalog,
  sectionPreview,
  searchCatalog,
  SECTION_PREVIEW_COUNT,
  CATALOG_SECTIONS
} from './appCatalog'
import type { AppCatalogGroup, AppCatalogItem } from './omiApi.generated'

function item(partial: Partial<AppCatalogItem> & { id: string }): AppCatalogItem {
  return { name: partial.id, category: 'other', ...partial }
}

function group(capabilityId: string, ids: string[]): AppCatalogGroup {
  return {
    capability: { id: capabilityId, title: capabilityId },
    data: ids.map((id) => item({ id }))
  }
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
