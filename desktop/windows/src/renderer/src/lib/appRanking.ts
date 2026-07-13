import type { App as AppEntry } from './omiApi.generated'

// Ranks an app by rating weighted by install count (log-damped). Used to order
// both category rows and search results so the most relevant apps surface first.
export function popularityScore(a: AppEntry): number {
  return (a.rating_avg ?? 0) * Math.log((a.installs ?? 1) + 1)
}

// Which relevance tier a search match falls in (lower = more relevant). A name
// match must beat raw popularity: search results are capped at SEARCH_LIMIT before
// render, so ordering purely by popularity can push a user's own low-popularity app
// past the cap and make it unreachable — e.g. they can't find it to toggle it off.
// Ranking exact/prefix name matches first guarantees that typing an app's name
// always surfaces it.
function nameMatchTier(a: AppEntry, q: string): number {
  const name = a.name?.toLowerCase() ?? ''
  if (name === q) return 0 // exact name match
  if (name.startsWith(q)) return 1 // name prefix match
  return 2 // matched elsewhere (name substring, description, category, author)
}

function matchesQuery(a: AppEntry, q: string): boolean {
  return Boolean(
    a.name?.toLowerCase().includes(q) ||
    a.description?.toLowerCase().includes(q) ||
    a.category?.toLowerCase().includes(q) ||
    a.author?.toLowerCase().includes(q)
  )
}

// Filters `apps` to those matching `rawQuery`, then orders them so the most
// relevant surface first (and stay within the render cap): exact name match, then
// name-prefix match, then by popularity. Pure and deterministic. Returns [] for an
// empty/whitespace query.
export function rankSearchResults(apps: AppEntry[], rawQuery: string): AppEntry[] {
  const q = rawQuery.trim().toLowerCase()
  if (!q) return []
  return apps
    .filter((a) => matchesQuery(a, q))
    .sort((a, b) => {
      const ta = nameMatchTier(a, q)
      const tb = nameMatchTier(b, q)
      if (ta !== tb) return ta - tb
      return popularityScore(b) - popularityScore(a)
    })
}
