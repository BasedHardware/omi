import { useCallback, useRef, useState } from 'react'
import { Ctx, type Entry } from './searchContext'

export function SettingsSearchProvider(props: { children: React.ReactNode }): React.JSX.Element {
  const [query, setQuery] = useState('')
  const entries = useRef(new Map<string, Entry>())
  // Bump to recompute tabHasMatch when the registry changes.
  const [, force] = useState(0)

  const register = useCallback((id: string, text: string, tab: string): void => {
    entries.current.set(id, { text: text.toLowerCase(), tab })
    force((n) => n + 1)
  }, [])
  const unregister = useCallback((id: string): void => {
    entries.current.delete(id)
    force((n) => n + 1)
  }, [])

  const q = query.trim().toLowerCase()
  const isSearching = q.length > 0
  const tabHasMatch = useCallback(
    (tab: string): boolean => {
      if (!q) return true
      for (const e of entries.current.values()) {
        if (e.tab === tab && e.text.includes(q)) return true
      }
      return false
    },
    [q]
  )

  return (
    <Ctx.Provider value={{ query, setQuery, isSearching, register, unregister, tabHasMatch }}>
      {props.children}
    </Ctx.Provider>
  )
}
