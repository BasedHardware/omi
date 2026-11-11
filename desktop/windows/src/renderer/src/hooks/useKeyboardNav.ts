import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { HOME_PATH, escapesToHome, pathForShortcut } from '../routes/manifest'
import { getPreferences } from '../lib/preferences'

/**
 * Global nav keys, ported from macOS:
 *
 * - Ctrl+1..6 / Ctrl+, jump to a page — Cmd+1..6 / Cmd+, on Mac (OmiApp.swift:163-214).
 *   1 Home, 2 Conversations, 3 Memories, 4 Tasks, 5 Rewind, 6 Apps, `,` Settings.
 * - Esc returns Home, but only from Conversations / Memories / Tasks / Rewind —
 *   not Settings, not Apps (DesktopHomeView.swift:1037-1044).
 *
 * Both are driven off routes/manifest.ts, so the key→page mapping lives with the
 * route rather than in a second list here.
 */
export function useKeyboardNav(): void {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  useEffect(() => {
    const isTyping = (e: KeyboardEvent): boolean => {
      const t = e.target as HTMLElement | null
      return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
    }

    const handler = (e: KeyboardEvent): void => {
      if (isTyping(e)) return

      if (e.metaKey || e.ctrlKey) {
        const path = pathForShortcut(e.key)
        if (path) {
          e.preventDefault()
          navigate(path)
        }
        return
      }

      if (e.key !== 'Escape') return
      // Esc→Home is the NEW design only; the legacy sidebar layout keeps Esc free
      // (macOS guards the same way: `guard !useLegacyHomeDesign`).
      if (getPreferences().useLegacyHomeDesign) return
      if (!escapesToHome(pathname)) return

      // Esc is contended: Rewind's in-page search (pages/Rewind.tsx:34) and Radix
      // modals both close on it via their OWN document listeners, and both call
      // preventDefault. We must not ALSO navigate home in those cases.
      //
      // Checking defaultPrevented inline doesn't work: document listeners fire in
      // registration order, and those two re-register whenever their open/closed
      // state flips (Rewind's effect depends on `showSearch`), which moves them
      // AFTER this one. So whether we'd see their preventDefault is a race.
      //
      // Deferring to a macrotask sidesteps the ordering entirely — by the time this
      // runs, every listener for the event has fired, so defaultPrevented is final.
      setTimeout(() => {
        if (e.defaultPrevented) return
        // Belt-and-braces for any dismissible layer that closes WITHOUT calling
        // preventDefault: a Radix dialog is in the DOM while open.
        if (document.querySelector('[role="dialog"]')) return
        navigate(HOME_PATH)
      }, 0)
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [navigate, pathname])
}
