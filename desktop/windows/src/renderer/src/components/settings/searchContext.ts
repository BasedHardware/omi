import { createContext, useContext, useEffect, useId } from 'react'

// Global Settings search. Rows register their searchable text (+ which tab they
// belong to). With a query present, each row self-hides when it doesn't match,
// and a whole tab panel hides when none of its rows match — giving cross-tab
// search without a separate hand-maintained manifest. All tab panels stay
// mounted (just visually hidden) so the registry is always complete.
//
// Contexts + hooks live here (a non-component module) so the provider file can
// export only its component and keep React Fast Refresh working.

export type Entry = { text: string; tab: string }

export type SearchCtx = {
  query: string
  setQuery: (q: string) => void
  isSearching: boolean
  register: (id: string, text: string, tab: string) => void
  unregister: (id: string) => void
  tabHasMatch: (tab: string) => boolean
}

export const Ctx = createContext<SearchCtx | null>(null)

// The tab a row currently lives under, supplied by SettingsTabPanel.
export const TabIdContext = createContext<string>('')

export function useSettingsSearch(): SearchCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSettingsSearch must be used within SettingsSearchProvider')
  return v
}

/**
 * Register a row's searchable text and report whether it should be visible for
 * the current query. Visible when there's no query, or the query is a
 * case-insensitive substring of the row's text.
 */
export function useSearchableRow(text: string): boolean {
  const id = useId()
  const tab = useContext(TabIdContext)
  const { register, unregister, query } = useSettingsSearch()
  useEffect(() => {
    register(id, text, tab)
    return () => unregister(id)
  }, [id, text, tab, register, unregister])
  const q = query.trim().toLowerCase()
  return q === '' || text.toLowerCase().includes(q)
}
