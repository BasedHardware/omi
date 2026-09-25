// Search state for the page: debounce, run, and keep the answer that belongs to
// what is in the box.
//
// The debounce is what stops a request per keystroke; SearchRunner is what stops
// an earlier answer landing on top of a later one when the debounce still lets
// two through (a paste, then a keystroke). Both are needed - a debounce alone
// still races, and a runner alone still floods.
//
// `searching` is DERIVED, not stored: it is simply "the results on screen do not
// belong to the text in the box". Storing it would mean setting state from the
// effect that starts the search, and any path that forgot to clear it would
// leave a permanent spinner over perfectly good results.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  SearchRunner,
  isSearchable,
  type SearchDeps,
  type SearchResults
} from '../lib/search/runSearch'

/** Quiet period before a search runs. Long enough that ordinary typing produces
 *  one request rather than one per letter, short enough that the results feel
 *  like they follow the keystroke. */
export const SEARCH_DEBOUNCE_MS = 180

export interface UseSearch {
  input: string
  setInput: (value: string) => void
  results: SearchResults | null
  searching: boolean
  /** Clears the box and everything on screen. */
  clear: () => void
}

export function useSearch(deps?: SearchDeps): UseSearch {
  const [input, setInput] = useState('')
  const [results, setResults] = useState<SearchResults | null>(null)
  const runner = useMemo(() => new SearchRunner(deps), [deps])
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      runner.cancel()
    }
  }, [runner])

  const trimmed = input.trim()

  useEffect(() => {
    if (!isSearchable(trimmed)) {
      // Nothing to run. Anything in flight belongs to a longer query that is no
      // longer on screen, so it is dropped rather than allowed to land.
      runner.cancel()
      return
    }
    const timer = setTimeout(() => {
      void runner.run(trimmed, (r) => {
        if (mounted.current) setResults(r)
      })
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [trimmed, runner])

  const clear = useCallback(() => {
    runner.cancel()
    setInput('')
    setResults(null)
  }, [runner])

  // Searching means the visible results were computed from different text.
  const searching = isSearchable(trimmed) && results?.query !== trimmed

  return { input, setInput, results, searching, clear }
}
