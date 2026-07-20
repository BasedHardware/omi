import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { panelRoutes, resolveRoute } from '../../routes/manifest'

// Every page stays mounted (inactive ones are just hidden) so switching tabs is
// instant. But the pages take no props, so without memo they ALL re-render on
// every navigation (MainViews re-renders when the pathname changes) — and that
// re-render reconciles heavy subtrees like the Memories brain map (an R3F scene)
// or large memory/conversation lists, which is what made tab switches lag.
// memo() makes a page re-render only from its OWN hooks/state, never from a
// parent navigation, so changing tabs just toggles the wrapper's visibility.
function panelClass(active: boolean): string {
  return active ? 'flex h-full min-h-0 flex-col' : 'hidden'
}

export function MainViews(): React.JSX.Element {
  const { pathname } = useLocation()

  // Mounting every panel up front (incl. the heavy Memories R3F brain map) on
  // first render blocks the main thread during the startup entrance animations
  // — a ~133ms frame stall (npm run bench:anim). Defer the inactive panels until
  // AFTER the animations have played. NOTE: requestIdleCallback is wrong here —
  // CSS animations run on the compositor, so the main thread looks idle *during*
  // them and the callback fires mid-animation, causing the very stall we're
  // avoiding. A fixed timeout that lands after the animations is what we want.
  // The active panel always mounts; any panel mounts on demand if navigated to
  // before hydration, so tab-switching stays instant once warmed.
  const [hydrateAll, setHydrateAll] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setHydrateAll(true), 1800)
    return () => clearTimeout(timer)
  }, [])

  const resolved = resolveRoute(pathname)
  if (resolved && 'redirectTo' in resolved) return <Navigate to={resolved.redirectTo} replace />
  if (resolved?.entry.kind === 'exclusive') return resolved.entry.render?.(resolved.params) ?? <></>

  const activePath = resolved?.entry.path

  return (
    <div className="flex h-full min-h-0 flex-col">
      {panelRoutes().map((entry) => {
        const active = entry.path === activePath
        const Panel = entry.Component
        return (
          <div key={entry.id} className={panelClass(active)}>
            {(active || hydrateAll) && Panel ? <Panel /> : null}
          </div>
        )
      })}
    </div>
  )
}
