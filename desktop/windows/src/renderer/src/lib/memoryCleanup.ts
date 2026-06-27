import type { Memory } from '../hooks/useMemories'
import { SCREEN_TAG } from './screenTag'

// Provenance tag the (removed) local app/file-index pipeline stamped on every
// memory it synthesized. macOS keeps app/file data in the local knowledge graph
// and NEVER as memories, so these don't belong on the account.
export const APP_INDEX_TAG = 'omi-app-index'

// Deterministic content template that pipeline wrote ("Uses <App>"). Matched
// only in its TIGHT template form — the literal word "Uses" followed by 1–4
// short name tokens and NOTHING else (no sentence punctuation, no trailing
// clause) — so a genuine user memory that merely starts with "Uses …" (e.g.
// "Uses Excel daily for budgeting and taxes.") is never swept up. This is the
// fallback for older builds that created the memory without the provenance tag.
const USES_TEMPLATE = /^uses(\s+[\w&+()'-]+){1,4}$/i

// File/project-index synthesis memories: the pipeline that summarized the local
// file index into memories wrote sentences like
//   "The user's local projects include ~/projects/omi-cheap-voice-demo/app/…"
// macOS keeps this in the knowledge graph, never as memories. Anchored on BOTH
// the generated stem AND a filesystem path so a normal memory that merely
// mentions a project (and contains no path) is never matched.
const LOCAL_INDEX_STEM =
  /the user['’]?s (local )?(projects?|files?|repos(itories)?|directories|folders|code(bases?)?)\b/i
const PATH_HINT = /[~/\\]/

// Other distinctive sentences the file-index synthesis produced. Each is
// machine-generated phrasing a real memory wouldn't use, so no path is required.
const INDEX_SENTENCES: RegExp[] = [
  /^a recently modified local file is named /i, // recent_file
  /\bthe user works on a local project named /i, // project
  /\bthe user['’]?s local files (show|indicate|include|reflect)\b/i, // technology
  /\bthe user has [\d,]+ local files indexed\b/i // profile
]

function isFileIndexMemory(content: string): boolean {
  if (LOCAL_INDEX_STEM.test(content) && PATH_HINT.test(content)) return true
  return INDEX_SENTENCES.some((re) => re.test(content))
}

// A memory is app/file-index-derived (and safe to remove) when it carries the
// provenance tag, matches the tight "Uses <App>" template, or is a local
// file/project-index synthesis sentence. None of these is real user knowledge —
// it's the on-disk index restated as memories, which the local KG already holds.
export function isAppIndexMemory(m: Memory): boolean {
  if (m.tags?.includes(APP_INDEX_TAG) || m.tags?.includes(SCREEN_TAG)) return true
  const c = (m.content ?? '').trim()
  return USES_TEMPLATE.test(c) || isFileIndexMemory(c)
}

export function appIndexMemoryIds(memories: Memory[]): string[] {
  return memories.filter(isAppIndexMemory).map((m) => m.id)
}

export type MemoryGroup = { key: string; count: number; samples: string[] }
export type MemoryBreakdown = {
  total: number
  // Grouped by tag (or '(untagged)'), most common first — read-only context so
  // the user can see what is and isn't matched before deleting anything.
  groups: MemoryGroup[]
  // The destructive target: memories isAppIndexMemory() would delete.
  appIndexCount: number
  appIndexSamples: string[]
}

function sample(content: string | undefined): string {
  return (content ?? '').slice(0, 100).replace(/\s+/g, ' ').trim()
}

// Pure, read-only summary for the maintenance UI. No network, no mutation.
export function summarizeMemories(memories: Memory[]): MemoryBreakdown {
  const counts = new Map<string, number>()
  const samples = new Map<string, string[]>()
  for (const m of memories) {
    const keys = m.tags?.length ? m.tags : ['(untagged)']
    for (const k of keys) {
      counts.set(k, (counts.get(k) ?? 0) + 1)
      const s = samples.get(k) ?? []
      if (s.length < 5 && m.content) s.push(sample(m.content))
      samples.set(k, s)
    }
  }
  const groups = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, count, samples: samples.get(key) ?? [] }))

  const appIndex = memories.filter(isAppIndexMemory)
  return {
    total: memories.length,
    groups,
    appIndexCount: appIndex.length,
    appIndexSamples: appIndex.slice(0, 8).map((m) => sample(m.content))
  }
}
