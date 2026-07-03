// Pure provenance/audit logic for the Memories page: classify where each memory
// came from, compose the audit filters (text + source + date), aggregate the
// "What Omi knows" counts, build the consequence preview for selective forget,
// and derive the provenance chain shown in the audit detail. Everything here is
// computed from fields the server already returns on GET /v3/memories — nothing
// is invented client-side, and every derivation degrades gracefully when a
// field is missing (memories created before the evidence pipeline lack most of
// them).
import type { Memory, MemoryEvidence } from '../hooks/useMemories'
import { APP_INDEX_TAG } from './memoryCleanup'
import { SCREEN_TAG } from './screenTag'

// Import tags stamped by the Settings integrations (IntegrationsTab/googleSync).
// Matched by prefix so note/profile variants group together.
const GMAIL_TAG_PREFIX = 'gmail/'
const STICKY_TAG_PREFIX = 'sticky_notes/'

export type MemorySourceKind =
  | 'screen'
  | 'conversation'
  | 'chat'
  | 'manual'
  | 'gmail'
  | 'sticky-notes'
  | 'file-index'
  | 'integration'
  | 'app'
  | 'unknown'

export const SOURCE_LABELS: Record<MemorySourceKind, string> = {
  screen: 'Screen capture',
  conversation: 'Conversation',
  chat: 'Omi chat',
  manual: 'Added by you',
  gmail: 'Gmail import',
  'sticky-notes': 'Sticky Notes',
  'file-index': 'File index',
  integration: 'Integration',
  app: 'App',
  unknown: 'Unknown source'
}

// Where did this memory come from? Resolution order: the desktop's own
// provenance tags (stamped at creation, most specific), then explicit record
// fields (manually_added / category), then the server evidence record, then
// weaker hints (conversation_id, app_id). A memory with none of these is
// honestly 'unknown' — never guessed.
export function memorySource(m: Memory): MemorySourceKind {
  const tags = m.tags ?? []
  if (tags.includes(SCREEN_TAG)) return 'screen'
  if (tags.includes(APP_INDEX_TAG)) return 'file-index'
  if (tags.some((t) => t.startsWith(GMAIL_TAG_PREFIX))) return 'gmail'
  if (tags.some((t) => t.startsWith(STICKY_TAG_PREFIX))) return 'sticky-notes'
  if (m.manually_added || m.category === 'manual') return 'manual'
  const ev = activeEvidence(m)[0]
  if (ev) {
    if (ev.source_signal === 'manual') return 'manual'
    if (ev.source_type === 'chat_exchange' || ev.source_signal === 'direct_user') return 'chat'
    if (ev.source_signal === 'integration' || ev.source_type?.startsWith('integration'))
      return 'integration'
    if (ev.source_type === 'conversation' || ev.source_signal === 'transcription')
      return 'conversation'
  }
  if (m.conversation_id) return 'conversation'
  if (m.app_id) return 'app'
  return 'unknown'
}

export type DateRange = 'any' | 'today' | '7d' | '30d'

export const DATE_RANGE_LABELS: Record<DateRange, string> = {
  any: 'Any time',
  today: 'Today',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days'
}

export function withinDateRange(createdAt: string, range: DateRange, now = new Date()): boolean {
  if (range === 'any') return true
  const t = new Date(createdAt).getTime()
  if (!Number.isFinite(t)) return false
  if (range === 'today') {
    const start = new Date(now)
    start.setHours(0, 0, 0, 0)
    return t >= start.getTime() && t <= now.getTime()
  }
  const days = range === '7d' ? 7 : 30
  return t >= now.getTime() - days * 86_400_000 && t <= now.getTime()
}

export type MemoryFilters = {
  text?: string
  source?: MemorySourceKind | 'all'
  range?: DateRange
}

export function hasActiveFilter(f: MemoryFilters): boolean {
  return !!f.text?.trim() || (!!f.source && f.source !== 'all') || (!!f.range && f.range !== 'any')
}

// Text, source, and date filters compose (AND). Text matching mirrors the
// page's original behavior: case-insensitive substring over content.
export function filterMemories(memories: Memory[], f: MemoryFilters, now = new Date()): Memory[] {
  const q = f.text?.trim().toLowerCase() ?? ''
  return memories.filter((m) => {
    if (q && !m.content?.toLowerCase().includes(q)) return false
    if (f.source && f.source !== 'all' && memorySource(m) !== f.source) return false
    if (f.range && f.range !== 'any' && !withinDateRange(m.created_at, f.range, now)) return false
    return true
  })
}

// Human summary of the active filters for the consequence preview, e.g.
// "Everything from screen capture, last 7 days". Null when nothing is filtered.
export function describeFilters(f: MemoryFilters): string | null {
  const parts: string[] = []
  if (f.source && f.source !== 'all') parts.push(`from ${SOURCE_LABELS[f.source].toLowerCase()}`)
  if (f.range && f.range !== 'any') parts.push(DATE_RANGE_LABELS[f.range].toLowerCase())
  const text = f.text?.trim()
  if (text) parts.push(`matching "${text}"`)
  if (parts.length === 0) return null
  return `Everything ${parts.join(', ')}`
}

export type SourceCount = { kind: MemorySourceKind; count: number }
export type CategoryCount = { category: string; count: number }

export function sourceCounts(memories: Memory[]): SourceCount[] {
  const counts = new Map<MemorySourceKind, number>()
  for (const m of memories) {
    const kind = memorySource(m)
    counts.set(kind, (counts.get(kind) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([kind, count]) => ({ kind, count }))
}

export function categoryCounts(memories: Memory[]): CategoryCount[] {
  const counts = new Map<string, number>()
  for (const m of memories) {
    const c = m.category || 'other'
    counts.set(c, (counts.get(c) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([category, count]) => ({ category, count }))
}

export function categoryLabel(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1)
}

// The server flags a memory backed by a single independent evidence group as
// uncertain (uncertainty_reasons: 'single_source'). Absence of the field means
// we don't know — no marker, never a guessed one.
export function isSeenOnce(m: Memory): boolean {
  return (m.uncertainty_reasons ?? []).includes('single_source')
}

// --- Selective forget -------------------------------------------------------

export type ForgetPreview = {
  count: number
  bySource: SourceCount[]
  byCategory: CategoryCount[]
}

export function forgetPreview(selected: Memory[]): ForgetPreview {
  return {
    count: selected.length,
    bySource: sourceCounts(selected),
    byCategory: categoryCounts(selected)
  }
}

// Honest time estimate for a paced bulk delete. deleteMemoriesPaced runs one
// delete per ~1.1s until the server's ~60/hour cap kicks in, after which 429s
// pace the rest at roughly one per minute.
export function estimateForgetSeconds(count: number): number {
  const PACE_SECONDS = 1.1
  const HOURLY_CAP = 60
  if (count <= 0) return 0
  if (count <= HOURLY_CAP) return count * PACE_SECONDS
  return HOURLY_CAP * PACE_SECONDS + (count - HOURLY_CAP) * 60
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return 'under a minute'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `about ${minutes} minute${minutes === 1 ? '' : 's'}`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m === 0 ? `about ${h} hour${h === 1 ? '' : 's'}` : `about ${h} h ${m} min`
}

// --- Audit detail -----------------------------------------------------------

export type ChainStep = {
  kind: 'capture' | 'conversation' | 'extraction' | 'corroboration'
  title: string
  sub?: string
  at?: string
  conversationId?: string
}

const CAPTURE_TITLES: Record<MemorySourceKind, string> = {
  screen: 'Captured from your screen',
  conversation: 'Heard in a conversation',
  chat: 'From a chat with Omi',
  manual: 'Added by you',
  gmail: 'Imported from Gmail',
  'sticky-notes': 'Imported from Sticky Notes',
  'file-index': 'Synthesized from your local file index',
  integration: 'From a connected integration',
  app: 'Created by an app',
  unknown: 'Origin not recorded'
}

function activeEvidence(m: Memory): MemoryEvidence[] {
  return (m.evidence ?? []).filter((e) => e.redaction_status !== 'tombstoned')
}

// The provenance chain rendered in the audit detail. Every step is derived
// from a real field on the record; steps whose backing fields are missing are
// omitted rather than faked, so the shortest honest chain is a single capture
// step timestamped by created_at.
export function provenanceChain(m: Memory): ChainStep[] {
  const steps: ChainStep[] = []
  const evidence = activeEvidence(m)
  const first = evidence[0]

  const capture: ChainStep = {
    kind: 'capture',
    title: CAPTURE_TITLES[memorySource(m)],
    at: first?.created_at ?? m.created_at
  }
  if (first?.client_device_id) capture.sub = `Device: ${first.client_device_id}`
  steps.push(capture)

  if (m.conversation_id) {
    steps.push({
      kind: 'conversation',
      title: 'Linked conversation',
      sub: 'The full conversation this memory was distilled from.',
      conversationId: m.conversation_id
    })
  }

  if (first?.extractor_id && first.extractor_id !== 'unknown') {
    const version =
      first.extractor_version && first.extractor_version !== 'unknown'
        ? ` ${first.extractor_version}`
        : ''
    const confidence =
      typeof m.capture_confidence === 'number'
        ? ` · capture confidence ${m.capture_confidence.toFixed(2)}`
        : ''
    steps.push({
      kind: 'extraction',
      title: 'Memory extracted',
      sub: `${first.extractor_id}${version}${confidence}`,
      at: m.created_at
    })
  }

  if (evidence.length > 1) {
    const groups = new Set(
      evidence.map((e) => e.independence_group || e.source_id).filter(Boolean)
    )
    const times = evidence
      .map((e) => e.created_at)
      .filter((t): t is string => !!t)
      .filter((t) => Number.isFinite(new Date(t).getTime()))
      .sort((a, b) => new Date(a).getTime() - new Date(b).getTime())
    steps.push({
      kind: 'corroboration',
      title: `Confirmed ${evidence.length - 1} more time${evidence.length > 2 ? 's' : ''}`,
      sub:
        groups.size > 1
          ? `Backed by ${evidence.length} evidence records from ${groups.size} independent sources.`
          : `Backed by ${evidence.length} evidence records.`,
      at: times[times.length - 1]
    })
  }

  return steps
}

export function relatedMemories(all: Memory[], m: Memory): Memory[] {
  if (!m.conversation_id) return []
  return all.filter((o) => o.id !== m.id && o.conversation_id === m.conversation_id)
}
