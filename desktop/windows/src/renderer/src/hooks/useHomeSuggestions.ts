import { useEffect, useState } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { auth } from '../lib/firebase'
import {
  composeSuggestions,
  readSuggestionsCache,
  refreshHomeSuggestions,
  suggestionsOwnerId
} from '../lib/intelligence/homeSuggestions'

/** The hub's ask-bar suggestion chips: the cached personalized set published
 *  immediately (no flash of the static defaults when a cache exists), then the
 *  at-most-daily refresh lands on top. Always composed: the lead chip plus two
 *  personalized-or-fallback questions (mac parity: HomeSuggestionComposer).
 *  Auth changes re-read the new owner's cache and re-run the refresh, so a
 *  sign-out/in while Home stays mounted never shows the previous account's
 *  questions. */
export function useHomeSuggestions(): string[] {
  const [personalized, setPersonalized] = useState<string[]>(
    () => readSuggestionsCache(suggestionsOwnerId())?.questions ?? []
  )

  useEffect(() => {
    let cancelled = false
    let refreshedOwner: string | null = null
    const refreshForCurrentOwner = (): void => {
      const owner = suggestionsOwnerId()
      if (owner === refreshedOwner) return
      refreshedOwner = owner
      setPersonalized(readSuggestionsCache(owner)?.questions ?? [])
      refreshHomeSuggestions()
        .then((questions) => {
          if (!cancelled && suggestionsOwnerId() === owner) setPersonalized(questions)
        })
        .catch(() => {})
    }
    refreshForCurrentOwner()
    const unsubscribe = onAuthStateChanged(auth, () => refreshForCurrentOwner())
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  return composeSuggestions(personalized)
}
