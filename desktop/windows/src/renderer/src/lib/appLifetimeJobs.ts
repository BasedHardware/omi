import { useEffect } from 'react'
import { maybeBuildLocalGraph } from './kgSynthesis'
import { maybeStartScreenSynthesis } from './screenSynthesis'
import { maybeStartInsightEngine } from './insightEngine'
import { maybeStartRetentionSweep } from './retentionSweep'

// The app's four background engines: knowledge-graph synthesis, screen synthesis,
// the insight engine, and the retention sweep.
//
// These are APP-LIFETIME, not page-scoped. They used to be kicked off from the Home
// PAGE's mount, which silently coupled "the user's landing page is Home" to "these
// engines run at all" — swap Home's design (the legacy-home flag) or land on another
// route first, and they would stop running in production with nothing to catch it.
// So they belong to the app shell, which mounts exactly once per signed-in,
// onboarded session in the main window. Do NOT move them back into a page.
//
// The graph build stays deferred past the entrance animations so its DB/synthesis
// work cannot stall them.
const GRAPH_BUILD_DELAY_MS = 1800

export function useAppLifetimeJobs(): void {
  useEffect(() => {
    const t = setTimeout(() => void maybeBuildLocalGraph(), GRAPH_BUILD_DELAY_MS)
    maybeStartScreenSynthesis()
    maybeStartInsightEngine()
    maybeStartRetentionSweep()
    return () => clearTimeout(t)
  }, [])
}
