import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

/**
 * Global keyboard shortcuts for nav. Each Cmd/Ctrl+<n> sends the user to the
 * corresponding sidebar item. Bound at the document level so it works
 * regardless of which panel is focused.
 */
const shortcuts: { combo: string; path: string }[] = [
  { combo: '1', path: '/home' },
  { combo: '2', path: '/conversations' },
  { combo: '3', path: '/tasks' },
  { combo: '4', path: '/memories' },
  { combo: '5', path: '/rewind' },
  { combo: '6', path: '/apps' },
  { combo: ',', path: '/settings' }
]

export function useKeyboardNav(): void {
  const navigate = useNavigate()
  useEffect(() => {
    const handler = (e: KeyboardEvent): void => {
      const mod = e.metaKey || e.ctrlKey
      if (!mod) return
      // Don't hijack typing in inputs.
      const t = e.target as HTMLElement | null
      if (
        t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      ) {
        return
      }
      const hit = shortcuts.find((s) => s.combo === e.key)
      if (hit) {
        e.preventDefault()
        navigate(hit.path)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [navigate])
}
