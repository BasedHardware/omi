import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { panelRoutes, resolveRoute } from '../../routes/manifest'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import { PanelErrorFallback } from '../ui/PanelErrorFallback'

// Content-area router. Every route — redirects, full-screen "exclusive" routes,
// and the mounted-but-hidden panel grid — is declared in routes/manifest.ts. This
// component is a behavior-preserving INTERPRETER of that manifest, not a place to
// add routes: add a page by appending a RouteEntry to the manifest.

function panelClass(active: boolean): string {
  return active ? 'flex h-full min-h-0 flex-col' : 'hidden'
}

export function MainViews(): React.JSX.Element {
  const { pathname } = useLocation()

  // Every panel stays mounted (inactive ones hidden) so tab switches are instant;
  // panel components are memo-wrapped in the manifest so they never re-render from
  // a parent navigation. Mounting every panel up front (incl. the heavy Memories
  // R3F brain map) on first render blocks the main thread during the startup
  // entrance animations (~133ms stall, npm run bench:anim), so defer the inactive
  // panels until AFTER the animations. requestIdleCallback is wrong here — CSS
  // animations run on the compositor, so the main thread looks idle *during* them
  // and the callback fires mid-animation; a fixed timeout that lands after the
  // animations is what we want. The active panel always mounts; any panel mounts
  // on demand if navigated to before hydration, so tab-switching stays instant.
  const [hydrateAll, setHydrateAll] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setHydrateAll(true), 1800)
    return () => clearTimeout(timer)
  }, [])

  const resolved = resolveRoute(pathname)

  // Redirect (e.g. '/', '/live', '/chat' -> '/home').
  if (resolved && 'redirectTo' in resolved) {
    return <Navigate to={resolved.redirectTo} replace />
  }

  // Exclusive full-screen route (LiveConversation, ConversationDetail): replaces
  // the whole panel grid, mounted only while matched (not memoized). The entry
  // renders itself from its own params, so its props stay type-checked.
  if (resolved && 'entry' in resolved && resolved.entry.kind === 'exclusive') {
    const { render, id } = resolved.entry
    // Fail loudly. Falling through to the panel grid would leave activeId pointing
    // at an exclusive route that no panel matches — a blank content area with no
    // error, which is the worst way to learn a manifest entry is malformed.
    if (!render) throw new Error(`exclusive route "${id}" has no render()`)
    return render(resolved.params)
  }

  // Panel grid: every panel mounted-hidden, the active one shown. Unknown
  // pathnames resolve to no active panel (blank content area, as before).
  const activeId = resolved && 'entry' in resolved ? resolved.entry.id : null

  return (
    <div className="flex h-full min-h-0 flex-col">
      {panelRoutes().map((entry) => {
        const Component = entry.Component
        const active = entry.id === activeId
        return (
          <div key={entry.id} className={panelClass(active)}>
            {/* Per-panel net: one page's render throw degrades to a small card
                while the sidebar/shell and the other mounted-hidden panels survive.
                Inert until it throws (renders <Component /> directly, no extra DOM
                node), and the mount condition is unchanged, so hydration timing and
                the manifest's panel memoization are untouched. */}
            {Component && (active || hydrateAll) && (
              <ErrorBoundary label={`panel:${entry.id}`} fallback={<PanelErrorFallback />}>
                <Component />
              </ErrorBoundary>
            )}
          </div>
        )
      })}
    </div>
  )
}
