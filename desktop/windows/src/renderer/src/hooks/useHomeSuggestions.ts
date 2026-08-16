import { useEffect, useState } from 'react'
import {
  composeSuggestions,
  readSuggestionsCache,
  refreshHomeSuggestions,
  suggestionsOwnerId
} from '../lib/intelligence/homeSuggestions'

/** The hub's ask-bar suggestion chips: the cached personalized set published
 *  immediately (no flash of the static defaults when a cache exists), then the
 *  at-most-daily refresh lands on top. Always composed: the lead chip plus two
 *  personalized-or-fallback questions (mac parity: HomeSuggestionComposer). */
export function useHomeSuggestions(): string[] {
  const [personalized, setPersonalized] = useState<string[]>(
    () => readSuggestionsCache(suggestionsOwnerId())?.questions ?? []
  )

  useEffect(() => {
    let cancelled = false
    refreshHomeSuggestions()
      .then((questions) => {
        if (!cancelled) setPersonalized(questions)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  return composeSuggestions(personalized)
}
