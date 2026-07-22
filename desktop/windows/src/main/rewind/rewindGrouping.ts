import type { RewindFrame, RewindSearchGroup } from '../../shared/types'
import { rewindMatchTerms } from './rewindSearchQuery'

/** Temporal window for clustering consecutive frames (matches macOS 30s). */
export const GROUP_WINDOW_MS = 30_000

/** The earliest position at which any of `terms` occurs in `text` (lowercased),
 *  and the matched term's length — or -1 when none match. */
function firstMatch(lowerText: string, terms: string[]): { idx: number; len: number } {
  let best = -1
  let len = 0
  for (const t of terms) {
    const i = lowerText.indexOf(t)
    if (i >= 0 && (best < 0 || i < best)) {
      best = i
      len = t.length
    }
  }
  return { idx: best, len }
}

/**
 * A context snippet around the first matched term. Uses the FTS-EXPANDED terms
 * (camelCase/digit/prefix parts), not the raw query: a frame surfaced only because
 * "ActivityPerformance" prefix-matched an OCR line reading "…Performance review…"
 * still gets a snippet centered on the match, where testing the raw literal
 * "activityperformance" would have found nothing and fallen back to an arbitrary
 * text head. Falls back to the head only when no expanded term is literally present.
 */
function snippet(text: string, terms: string[]): string {
  const { idx, len } = firstMatch(text.toLowerCase(), terms)
  if (idx < 0) return text.slice(0, 80)
  const start = Math.max(0, idx - 30)
  return (start > 0 ? '…' : '') + text.slice(start, idx + len + 30).trim() + '…'
}

/**
 * Cluster a flat frame list into groups: consecutive frames within
 * GROUP_WINDOW_MS of the group's start that share the same app + window title.
 *
 * Frames are clustered chronologically (a group is a stretch of time), but the
 * GROUPS come back in the RELEVANCE order of the input — a group ranks by its
 * best-ranked member.
 *
 * That last part is the whole contract, and it used to be thrown away: this
 * function re-sorted everything by timestamp, so `mergeRewindSearchResults`'
 * carefully preserved "FTS leads, vector hits only append" ordering never
 * survived to the UI. A 0.51-similarity semantic hit from this morning displayed
 * ABOVE an exact keyword match from last Tuesday. (Before semantic search that
 * was harmless — every result was a keyword hit, so chronological was as good an
 * order as any. Adding a second, weaker source of results is what turned the
 * discarded ordering into a correctness bug.)
 */
/** Options for annotating grouped results. */
export type GroupOptions = {
  /** The frame ids that were KEYWORD (FTS) hits. When given, a group with none of
   *  these ids is flagged `matchedSemantically` — it exists only via vector recall. */
  keywordIds?: Set<number>
}

export function groupFrames(
  frames: RewindFrame[],
  query: string,
  opts: GroupOptions = {}
): RewindSearchGroup[] {
  const { keywordIds } = opts
  // Expanded literal terms, computed once — used for both representative
  // selection and the snippet so a sub-part-only match still highlights (M-2).
  const terms = rewindMatchTerms(query)
  // Relevance rank = position in the input. Captured BEFORE the chronological
  // sort below, which exists only to make time-contiguous clustering possible.
  const rankOf = new Map<number, number>()
  frames.forEach((f, i) => {
    if (f.id != null && !rankOf.has(f.id)) rankOf.set(f.id, i)
  })
  const rankOfGroup = (g: RewindSearchGroup): number =>
    Math.min(...g.frames.map((f) => (f.id != null ? (rankOf.get(f.id) ?? Infinity) : Infinity)))

  const sorted = [...frames].sort((a, b) => a.ts - b.ts)
  const groups: RewindSearchGroup[] = []
  let current: RewindFrame[] = []

  const flush = (): void => {
    if (current.length === 0) return
    const first = current[0]
    const last = current[current.length - 1]
    const rep =
      current.find((f) => {
        const lower = f.ocrText.toLowerCase()
        return terms.some((t) => lower.includes(t))
      }) ?? last
    // Purely semantic when no member was a keyword hit (only meaningful once the
    // caller supplies the keyword id set — i.e. on the merged phase-2 results).
    const matchedSemantically = keywordIds
      ? current.every((f) => f.id == null || !keywordIds.has(f.id))
      : false
    groups.push({
      id: `${first.app}-${first.ts}`,
      app: first.app,
      windowTitle: first.windowTitle,
      startTs: first.ts,
      endTs: last.ts,
      frames: [...current],
      representative: rep,
      matchSnippet: snippet(rep.ocrText, terms),
      matchedSemantically
    })
    current = []
  }

  for (const f of sorted) {
    if (current.length === 0) {
      current.push(f)
      continue
    }
    const first = current[0]
    const prev = current[current.length - 1]
    const sameContext = prev.app === f.app && prev.windowTitle === f.windowTitle
    const withinWindow = f.ts - first.ts <= GROUP_WINDOW_MS
    if (sameContext && withinWindow) current.push(f)
    else {
      flush()
      current.push(f)
    }
  }
  flush()
  // Strongest group first; newest first only to break a tie (two groups whose
  // best members were adjacent in the input, which the merge never produces).
  return groups.sort((a, b) => rankOfGroup(a) - rankOfGroup(b) || b.startTs - a.startTs)
}
