// Pure, dependency-free filtering + date-grouping for the Conversations list.
// Extracted so the composition rules (folder + starred + date + type + search) and
// the Today/Yesterday/date bucketing are unit-testable without React or the DOM.
// The Conversations page composes these over its merged cloud+local rows.

import { startOfLocalDay } from '../localDay'
import type { ConversationRow } from '../pageCache'

/** Windows-ahead type filter: chat threads vs recordings. Cloud conversations are
 *  recordings (they sync from local recordings), so they count as 'recording'. */
export type FilterKind = 'all' | 'chat' | 'recording'

/** The selected chip in the folder strip. 'all'/'starred' are fixed; 'folder'
 *  carries a backend folder id. */
export type FolderFilter = { kind: 'all' } | { kind: 'starred' } | { kind: 'folder'; id: string }

/** An inclusive [start, end] window in epoch ms (either bound may be null/open). */
export type DateRange = { start: number | null; end: number | null }

export type ConversationFilters = {
  folder: FolderFilter
  type: FilterKind
  query: string
  dateRange: DateRange
}

export const NO_DATE_RANGE: DateRange = { start: null, end: null }

/** A row supports the backend-backed star/folder/merge actions only if it is a
 *  real cloud conversation (has a backend id). Local-only recordings and chat rows
 *  don't — the star/folder/merge affordances are hidden/disabled for them, and a
 *  folder/starred FILTER can never match them. */
export function isCloudBacked(r: ConversationRow): boolean {
  return r.source === 'cloud' && !r.pending
}

/** Folder/starred are cloud concepts — a local row can never match them, so it is
 *  hidden whenever such a filter is active. 'all' shows everything. */
export function matchesFolder(r: ConversationRow, folder: FolderFilter): boolean {
  switch (folder.kind) {
    case 'all':
      return true
    case 'starred':
      return isCloudBacked(r) && r.starred === true
    case 'folder':
      return isCloudBacked(r) && r.folderId === folder.id
  }
}

export function matchesType(r: ConversationRow, type: FilterKind): boolean {
  if (type === 'chat') return r.localKind === 'chat'
  // 'recording' = everything that isn't a chat (cloud conversations + local
  // recordings). This is why a synced recording still shows under "Recordings".
  if (type === 'recording') return r.localKind !== 'chat'
  return true
}

export function matchesQuery(r: ConversationRow, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return (r.title?.toLowerCase() ?? '').includes(q) || (r.preview?.toLowerCase() ?? '').includes(q)
}

export function matchesDateRange(r: ConversationRow, range: DateRange): boolean {
  if (range.start != null && r.sortAt < range.start) return false
  if (range.end != null && r.sortAt > range.end) return false
  return true
}

export function matchesFilters(r: ConversationRow, f: ConversationFilters): boolean {
  return (
    matchesFolder(r, f.folder) &&
    matchesType(r, f.type) &&
    matchesQuery(r, f.query) &&
    matchesDateRange(r, f.dateRange)
  )
}

export function applyFilters(rows: ConversationRow[], f: ConversationFilters): ConversationRow[] {
  return rows.filter((r) => matchesFilters(r, f))
}

/** True when any non-default filter is set (drives the "clear all" affordance). */
export function hasActiveFilters(f: ConversationFilters): boolean {
  return (
    f.folder.kind !== 'all' ||
    f.type !== 'all' ||
    f.query.trim() !== '' ||
    f.dateRange.start != null ||
    f.dateRange.end != null
  )
}

// --- Merge eligibility ---

/** The cloud-backed subset of a selection (the only rows mergeable by id). */
export function mergeableRows(rows: ConversationRow[]): ConversationRow[] {
  return rows.filter(isCloudBacked)
}

/** Merge requires ≥2 cloud conversations. */
export function canMerge(rows: ConversationRow[]): boolean {
  return mergeableRows(rows).length >= 2
}

// --- Backend list query ---

/** List-query params for the cloud fetch. Folder/starred/date are applied
 *  server-side (the /v1/conversations query supports them, so pagination stays
 *  correct); type + search stay client-side over the merged rows. Dates serialize
 *  to ISO strings spanning the selected days. */
export function buildConversationQuery(
  folder: FolderFilter,
  dateRange: DateRange,
  limit = 100,
  offset = 0
): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = { limit, offset }
  if (folder.kind === 'starred') params.starred = true
  if (folder.kind === 'folder') params.folder_id = folder.id
  if (dateRange.start != null) params.start_date = new Date(dateRange.start).toISOString()
  if (dateRange.end != null) params.end_date = new Date(dateRange.end).toISOString()
  return params
}

// --- Date grouping ---

export type DateSection = {
  /** Stable React key (the day's local-midnight epoch ms). */
  key: string
  /** "Today" | "Yesterday" | a locale-formatted date. */
  label: string
  rows: ConversationRow[]
}

// Local-day helpers live in ../localDay (one copy of the local-midnight rule);
// re-exported here because this module is the historical import site.
export { startOfLocalDay, endOfLocalDay } from '../localDay'

function sectionLabel(dayStart: number, todayStart: number): string {
  if (dayStart === todayStart) return 'Today'
  // Yesterday is a calendar-day relationship, not `todayStart - 24h`: on the two
  // DST-transition days a local day is 23h/25h long, so the fixed offset lands
  // an hour off the neighbor day's midnight and the label silently degrades to a
  // date. Pinned by contracts/parity/section_labels.json.
  const yesterday = new Date(todayStart)
  yesterday.setDate(yesterday.getDate() - 1)
  yesterday.setHours(0, 0, 0, 0)
  if (dayStart === yesterday.getTime()) return 'Yesterday'
  return new Date(dayStart).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  })
}

/** Group rows into day sections sorted Today→Yesterday→older, rows within a
 *  section newest-first. `now` is injectable for deterministic tests. */
export function groupConversationsByDate(
  rows: ConversationRow[],
  now: number = Date.now()
): DateSection[] {
  const todayStart = startOfLocalDay(now)
  const byDay = new Map<number, ConversationRow[]>()
  for (const r of rows) {
    const day = startOfLocalDay(r.sortAt)
    const bucket = byDay.get(day)
    if (bucket) bucket.push(r)
    else byDay.set(day, [r])
  }
  return [...byDay.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([day, dayRows]) => ({
      key: String(day),
      label: sectionLabel(day, todayStart),
      rows: dayRows.sort((a, b) => b.sortAt - a.sortAt)
    }))
}
