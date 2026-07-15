import type { Memory } from '../hooks/useMemories'

// Pure, framework-free filtering/derivation helpers for the Memories page, kept
// out of the component so they're cheap to unit-test and reuse.

// The four product categories, in the order the filter renders them. Raw backend
// values: `manual`, `system` (facts About You), `interesting` (external
// Insights), `workflow`. Legacy values are folded to `system` on write by the
// backend, so a normalize step here only has to defend against the unexpected.
export type MemoryCategory = 'manual' | 'system' | 'interesting' | 'workflow'

export const MEMORY_CATEGORIES: readonly MemoryCategory[] = [
  'manual',
  'system',
  'interesting',
  'workflow'
]

export const CATEGORY_LABEL: Record<MemoryCategory, string> = {
  manual: 'Manual',
  system: 'About You',
  interesting: 'Insights',
  workflow: 'Workflow'
}

// Normalize a memory's raw category to one of the four product categories.
// Anything unrecognized (or absent) reads as Insights, matching the backend's
// own "unknown → interesting" default so the two never disagree.
export function categoryOf(m: Memory): MemoryCategory {
  const c = m.category
  if (c === 'manual' || c === 'system' || c === 'interesting' || c === 'workflow') return c
  return 'interesting'
}

// The layer filter's cases. `default` is the baseline (Short-term + Long-term,
// i.e. everything that isn't archived); the others narrow to a single layer.
// Gated behind canonicalLifecycleExposed at the call site — legacy/untiered
// memories carry no `layer`, so this filter only ever runs against tiered data.
export type MemoryLayerFilter = 'default' | 'short_term' | 'long_term' | 'archive'

export const LAYER_FILTERS: readonly MemoryLayerFilter[] = [
  'default',
  'short_term',
  'long_term',
  'archive'
]

export const LAYER_FILTER_LABEL: Record<MemoryLayerFilter, string> = {
  default: 'Default',
  short_term: 'Short-term',
  long_term: 'Long-term',
  archive: 'Archive'
}

export const LAYER_FILTER_DESC: Record<MemoryLayerFilter, string> = {
  default: 'Short-term + Long-term',
  short_term: 'Fresh source-backed memories',
  long_term: 'Stable memories',
  archive: 'Explicit archive search'
}

function matchesLayer(m: Memory, filter: MemoryLayerFilter): boolean {
  if (filter === 'default') return m.layer !== 'archive'
  return m.layer === filter
}

// A short, human layer name for the per-card tier badge. Returns null for
// untiered/legacy memories so the badge is omitted entirely (Mac's
// `tierIsExplicit` rule).
export function layerLabel(m: Memory): string | null {
  switch (m.layer) {
    case 'short_term':
      return 'Short-term'
    case 'long_term':
      return 'Long-term'
    case 'archive':
      return 'Archive'
    default:
      return null
  }
}

// A memory is "new" for its first minute — drives the New badge, mirroring Mac's
// 60s window. `now` is injectable for tests.
export const NEW_MEMORY_WINDOW_MS = 60_000

export function isNewMemory(m: Memory, now: number = Date.now()): boolean {
  const created = new Date(m.created_at).getTime()
  if (Number.isNaN(created)) return false
  return now - created < NEW_MEMORY_WINDOW_MS && now - created >= 0
}

// A memory whose content is an encrypted/locked placeholder rather than real
// text. The backend truncates locked content and prefixes protected blobs;
// these render as a "Protected memory" placeholder instead of leaking the blob.
export function isProtectedContent(content: string): boolean {
  const t = content.trimStart()
  return t.startsWith('[Protected') || t.startsWith('[Encrypted')
}

// "3h ago · Jan 4, 2:15 PM" — a relative age plus an absolute stamp, matching
// Mac's memory-card footer. `now` is injectable for tests.
export function formatMemoryDate(created_at: string, now: number = Date.now()): string {
  const d = new Date(created_at)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Math.max(0, now - d.getTime())
  const mins = Math.floor(diff / 60_000)
  const hours = Math.floor(diff / 3_600_000)
  const days = Math.floor(diff / 86_400_000)
  let rel: string
  if (mins < 1) rel = 'just now'
  else if (mins < 60) rel = `${mins}m ago`
  else if (hours < 24) rel = `${hours}h ago`
  else if (days < 7) rel = `${days}d ago`
  else rel = ''
  const sameYear = d.getFullYear() === new Date(now).getFullYear()
  const abs = d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
    hour: 'numeric',
    minute: '2-digit'
  })
  return rel ? `${rel} · ${abs}` : abs
}

export type MemoryFilters = {
  search: string
  // Empty set = all categories. Multi-select, matching Mac's category popover.
  categories: Set<MemoryCategory>
  // Applied only when the tier filter is exposed; otherwise pass 'default'.
  layer: MemoryLayerFilter
  // Applied only when the device filter is exposed.
  thisDeviceOnly: boolean
  thisDeviceId?: string | null
}

function matchesThisDevice(m: Memory, deviceId?: string | null): boolean {
  if (!deviceId) return true
  if (m.primary_capture_device === deviceId) return true
  return (m.capture_device_ids ?? []).includes(deviceId)
}

// Apply every active filter to a memory list. Search matches content
// case-insensitively; category is OR within the selected set; layer and
// this-device narrow further. Order is preserved (caller sorts upstream).
export function filterMemories(memories: Memory[], f: MemoryFilters): Memory[] {
  const q = f.search.trim().toLowerCase()
  return memories.filter((m) => {
    if (q && !m.content?.toLowerCase().includes(q)) return false
    if (f.categories.size > 0 && !f.categories.has(categoryOf(m))) return false
    if (!matchesLayer(m, f.layer)) return false
    if (f.thisDeviceOnly && !matchesThisDevice(m, f.thisDeviceId)) return false
    return true
  })
}
