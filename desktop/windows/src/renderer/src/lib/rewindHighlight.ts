// Split a search-result snippet into matched / unmatched runs so the results list
// can bold the parts that matched — the renderer-side companion to the grouping
// snippet (which centers the text on the first match). Pure + DOM-free for testing.

export type HighlightSegment = { text: string; match: boolean }

/**
 * Break `text` into consecutive segments, flagging the runs that (case-insensitively)
 * equal one of `terms`. Overlapping/adjacent matches are merged left-to-right,
 * longest-term-first at each position so "Performance" wins over "perf". `terms`
 * must already be lowercased (as `highlightTerms` returns them).
 */
export function highlightSegments(text: string, terms: string[]): HighlightSegment[] {
  const active = terms.filter((t) => t.length > 0)
  if (active.length === 0 || text === '') return text ? [{ text, match: false }] : []
  // Longest first so a match consumes the largest possible run at each position.
  const byLen = [...active].sort((a, b) => b.length - a.length)
  const lower = text.toLowerCase()
  const segs: HighlightSegment[] = []
  let plainStart = 0
  let i = 0
  const pushPlain = (end: number): void => {
    if (end > plainStart) segs.push({ text: text.slice(plainStart, end), match: false })
  }
  while (i < text.length) {
    const hit = byLen.find((t) => lower.startsWith(t, i))
    if (hit) {
      pushPlain(i)
      segs.push({ text: text.slice(i, i + hit.length), match: true })
      i += hit.length
      plainStart = i
    } else {
      i++
    }
  }
  pushPlain(text.length)
  return segs
}
