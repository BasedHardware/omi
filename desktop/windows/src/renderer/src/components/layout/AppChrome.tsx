import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { PageChromeBar } from './PageChromeBar'
import { showsPageChrome } from '../../routes/manifest'
import { useKeyboardNav } from '../../hooks/useKeyboardNav'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'

// The app's navigation chrome, ported from macOS's shipped model.
//
// The nav rail is RETIRED, the way macOS retired it: kept behind the legacy flag
// rather than deleted. macOS gates it identically —
//   showsPrimarySidebar = useLegacyHomeDesign && !hideSidebar
// (DesktopHomeView.swift:566-568) — and `useLegacyHomeDesign` defaults false, so the
// rail never mounts in the shipped design. Pages are reached instead via the Home
// stat ribbon's tiles, the PageChromeBar "Home" pill, and Ctrl+1..6.
//
// Settings keeps its own full-screen tab rail, so it suppresses the sidebar even in
// legacy mode — that's the `!hideSidebar` half of Mac's expression.
export function AppChrome({ children }: { children: React.ReactNode }): React.JSX.Element {
  const { pathname } = useLocation()

  const [legacy, setLegacy] = useState<boolean>(() => getPreferences().useLegacyHomeDesign ?? false)
  useEffect(() => onPreferencesChange((p) => setLegacy(p.useLegacyHomeDesign ?? false)), [])

  const hideSidebar = pathname === '/settings'
  const showsPrimarySidebar = legacy && !hideSidebar

  // Chrome rides above every page except Home, and only in the new design — macOS:
  // `!useLegacyHomeDesign && selectedIndex != dashboard` (DesktopHomeView.swift:908).
  const showsChrome = !legacy && showsPageChrome(pathname)

  // Ctrl+1..6 / Ctrl+, page jumps, and Esc→Home from the four pages macOS allows.
  useKeyboardNav()

  return (
    <div className="flex min-h-0 flex-1">
      {showsPrimarySidebar && <Sidebar />}
      {/* With the rail gone this reclaims the full window width (flex-1). */}
      <main className="page-outlet relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden">
        {showsChrome && <PageChromeBar />}
        <div className="min-h-0 flex-1">{children}</div>
      </main>
    </div>
  )
}
