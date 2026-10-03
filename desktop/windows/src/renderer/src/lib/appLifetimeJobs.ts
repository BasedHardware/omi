import { useEffect } from 'react'
import { startAiProfileHost } from './aiProfileHost'
import { startRewindEmbedHost } from './rewindEmbedHost'
import { startPiMonoAuthHost } from './piMonoAuthHost'
import { maybeBuildLocalGraph } from './kgSynthesis'
import { maybeStartScreenSynthesis } from './screenSynthesis'
import { maybeStartRetentionSweep } from './retentionSweep'

// The app's three background engines: knowledge-graph synthesis, screen synthesis,
// and the retention sweep.
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
    // These KEEP services used to bootstrap through the misnamed Insight engine.
    // Their idempotent token relays belong to the signed-in shell independently.
    startAiProfileHost()
    startRewindEmbedHost()
    startPiMonoAuthHost()
    maybeStartScreenSynthesis()
    maybeStartRetentionSweep()
    return () => clearTimeout(t)
  }, [])
}
