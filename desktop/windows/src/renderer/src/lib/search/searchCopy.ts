// Every string the search page shows, as pure functions.
//
// They live here rather than inline in JSX for one reason: the count line is the
// only thing telling someone whether they are looking at all of their matches or
// a slice of them, so each branch of it is worth a test. A count that quietly
// reads "20" when 300 matched is the search-box equivalent of losing data — the
// person stops looking, believing they have seen everything.

import type { SearchCorpus, SearchResults, SearchSlice } from './runSearch'
import { CORPUS_ORDER, MIN_QUERY_LENGTH } from './runSearch'

const formatCount = (n: number): string => n.toLocaleString()

/**
 * The line under a corpus heading.
 *
 * - failed          -> names the failure, so an empty list is never mistaken for
 *                      "you have nothing about that"
 * - nothing matched -> "No matches"
 * - all shown       -> the exact count
 * - some shown      -> "Showing N of M", with a trailing `+` when M is a floor
 */
export function corpusCountLabel(slice: SearchSlice): string {
  if (slice.failed) return 'Could not be searched'
  if (slice.total === 0 && slice.hits.length === 0) return 'No matches'
  const shown = slice.hits.length
  const total = Math.max(slice.total, shown)
  const totalText = `${formatCount(total)}${slice.atLeast ? '+' : ''}`
  if (shown >= total && !slice.atLeast) {
    return shown === 1 ? '1 match' : `${formatCount(shown)} matches`
  }
  return `Showing ${formatCount(shown)} of ${totalText}`
}

/** True when every corpus came back empty and none of them failed. */
export function isEmptyResult(results: SearchResults): boolean {
  return CORPUS_ORDER.every((c) => results[c].hits.length === 0 && !results[c].failed)
}

/** True when no corpus could be searched at all. */
export function isTotalFailure(results: SearchResults): boolean {
  return CORPUS_ORDER.every((c) => results[c].failed)
}

/** Corpora that could not be searched, in presentation order. */
export function failedCorpora(results: SearchResults): SearchCorpus[] {
  return CORPUS_ORDER.filter((c) => results[c].failed)
}

export type SearchPhase =
  | { kind: 'prompt' }
  | { kind: 'tooShort' }
  | { kind: 'searching' }
  | { kind: 'unavailable' }
  | { kind: 'empty'; query: string }
  | { kind: 'results' }

/**
 * Which state the page is in. Kept as one function so the page cannot render two
 * states at once, and so the precedence is written down instead of emerging from
 * the order of JSX conditionals.
 *
 * `searching` wins over `empty`: showing "nothing found" while a request is
 * still open tells someone their data is missing when it simply has not arrived.
 */
export function searchPhase(args: {
  input: string
  searching: boolean
  results: SearchResults | null
}): SearchPhase {
  const trimmed = args.input.trim()
  if (trimmed.length === 0) return { kind: 'prompt' }
  if (trimmed.length < MIN_QUERY_LENGTH) return { kind: 'tooShort' }
  if (args.searching) return { kind: 'searching' }
  if (args.results === null) return { kind: 'searching' }
  if (isTotalFailure(args.results)) return { kind: 'unavailable' }
  if (isEmptyResult(args.results)) return { kind: 'empty', query: args.results.query }
  return { kind: 'results' }
}

export const COPY = {
  placeholder: 'Search conversations, memories, tasks and screen',
  prompt: 'Search everything Omi has kept for you.',
  tooShort: `Type at least ${MIN_QUERY_LENGTH} characters.`,
  searching: 'Searching…',
  unavailable: 'Search is unavailable right now. Check your connection and try again.',
  /** Named after the text that was actually searched, not the live input. */
  empty: (query: string): string => `Nothing matches “${query}”.`,
  partial: (corpora: SearchCorpus[], labels: Record<SearchCorpus, string>): string =>
    `${corpora.map((c) => labels[c]).join(' and ')} could not be searched, so these results are incomplete.`
} as const
