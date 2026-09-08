import type { AppCatalogGroup, AppCatalogItem } from './omiApi.generated'
import { rankSearchResults } from './appRanking'

// Number of apps shown in a capability section before the "See more" affordance.
// Matches macOS AppsPage (`Array(...prefix(6))`).
export const SECTION_PREVIEW_COUNT = 6

// The fixed set of capability sections the Apps page renders, in the exact order
// macOS renders them (AppsPage.swift): popular first, then external integrations,
// then proactive/realtime notifications.
// - The 'popular' section title is "Other" because that is the literal string
//   macOS renders (AppsPage.swift:246 — `title: "Other"`), even though the backend
//   labels the capability "Featured". Keep it as "Other" for parity.
// - macOS fetches the `chat`, `memories`, and `tasks` groups too but renders NO
//   Apps-page section for them (chat/memories warm the chat picker; macOS has no
//   Tasks section at all), so they are intentionally omitted here and fold into the
//   deduped "all apps" union instead.
export interface CatalogSectionDef {
  capabilityId: string
  title: string
}

export const CATALOG_SECTIONS: CatalogSectionDef[] = [
  { capabilityId: 'popular', title: 'Other' },
  { capabilityId: 'external_integration', title: 'Integrations' },
  { capabilityId: 'proactive_notification', title: 'Realtime Notifications' }
]

export interface CatalogSection extends CatalogSectionDef {
  // Apps in this capability group, in the backend-provided order (no client sort —
  // macOS keeps the server order within a group).
  apps: AppCatalogItem[]
  // Whether there are more apps than the preview count (drives the See more control).
  hasMore: boolean
  // Total apps in this group on the server (from group.pagination.total). May exceed
  // apps.length when the group was truncated by the request's per-group limit.
  total: number
  // True when the server has more apps in this group than were returned (the limit
  // cut the group short). Callers should surface/log this — a capped fetch must not
  // silently drop apps.
  truncated: boolean
}

export interface Catalog {
  sections: CatalogSection[]
  // Deduped union of every app across all groups, in group-iteration order. Backs
  // the category filter options and the client search fallback.
  allApps: AppCatalogItem[]
}

// Walks the v2 `/v2/apps` grouped response into macOS's fixed-order sections plus a
// deduped union of every app. Pure and deterministic. Backend order is preserved
// within each group and across the union (matching macOS's fetchApps dedupe order).
// Per-group pagination (total/hasNext) is carried through so callers can detect and
// surface truncation — the request's `limit` applies PER GROUP, not overall.
export function buildCatalog(groups: AppCatalogGroup[] | undefined): Catalog {
  const byCapability = new Map<string, AppCatalogGroup>()
  const allApps: AppCatalogItem[] = []
  const seen = new Set<string>()

  for (const group of groups ?? []) {
    const capId = group.capability?.id
    const data = group.data ?? []
    if (capId && !byCapability.has(capId)) byCapability.set(capId, group)
    for (const app of data) {
      if (!app.id || seen.has(app.id)) continue
      seen.add(app.id)
      allApps.push(app)
    }
  }

  const sections: CatalogSection[] = CATALOG_SECTIONS.map((def) => {
    const group = byCapability.get(def.capabilityId)
    const apps = group?.data ?? []
    const total = group?.pagination?.total ?? apps.length
    const truncated = group?.pagination?.hasNext ?? total > apps.length
    return { ...def, apps, hasMore: apps.length > SECTION_PREVIEW_COUNT, total, truncated }
  }).filter((s) => s.apps.length > 0)

  return { sections, allApps }
}

// Merges the approved-only v2 union with the per-user v1 `/apps` list into a single
// deduped lookup for the Installed view. v2 excludes a user's private/unapproved/
// tester apps, so sourcing Installed from v2 alone would silently drop apps the user
// has enabled. v1 wins for shared ids (it carries the authoritative user-private
// record). Order: v2 first, then v1-only appended.
export function mergeAppPool(
  v2Union: AppCatalogItem[],
  v1Apps: AppCatalogItem[]
): AppCatalogItem[] {
  const pool = new Map<string, AppCatalogItem>()
  for (const a of v2Union) if (a.id) pool.set(a.id, a)
  for (const a of v1Apps) if (a.id) pool.set(a.id, a) // v1 wins for shared ids
  return [...pool.values()]
}

// The slice of a section's apps to render given whether it is expanded: the first
// SECTION_PREVIEW_COUNT when collapsed, all of them when expanded.
export function sectionPreview(apps: AppCatalogItem[], expanded: boolean): AppCatalogItem[] {
  return expanded ? apps : apps.slice(0, SECTION_PREVIEW_COUNT)
}

export interface SearchResult {
  apps: AppCatalogItem[]
  // True when the remote search endpoint failed and results came from the local
  // client-side fallback over already-loaded apps.
  usedFallback: boolean
}

// Runs a catalog search: routes to the remote `/v2/apps/search` endpoint via
// `fetchRemote`, falling back to a client-side rank of `localApps` if the endpoint
// throws (network/401/etc.). Empty/whitespace queries short-circuit to no results.
// Pure with respect to its injected fetcher, so both paths are unit-testable.
export async function searchCatalog(
  rawQuery: string,
  fetchRemote: (query: string) => Promise<AppCatalogItem[]>,
  localApps: AppCatalogItem[]
): Promise<SearchResult> {
  const query = rawQuery.trim()
  if (!query) return { apps: [], usedFallback: false }
  try {
    const apps = await fetchRemote(query)
    return { apps, usedFallback: false }
  } catch {
    return { apps: rankSearchResults(localApps, query), usedFallback: true }
  }
}
