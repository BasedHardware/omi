// Slim renderer entry for the toast window (#/insight-toast). It mounts ONLY the
// InsightToast component tree — not the full app (MainViews, three.js orb,
// onnxruntime VAD, all pages). Every aux window used to load index.html's full
// SPA (~200 MB RSS each); this entry loads a fraction. See insight-toast.html and
// perf/win-slim-aux-windows.
//
// Fonts: the toast text inherits --font-app (Inter Variable) from globals.css;
// it uses no serif or monospace face, so only Inter (roman + italic, to satisfy
// globals.css `font-synthesis: none`) is imported — dropping the unused JetBrains
// Mono / Newsreader faces is invisible here. The ancestor tree mirrors what
// InsightToast had inside App.tsx today.
import '@fontsource-variable/inter/opsz.css'
import '@fontsource-variable/inter/opsz-italic.css'
import './styles/globals.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/electron/renderer'
import { HashRouter } from 'react-router-dom'
import { InsightToast } from './components/insight/InsightToast'
import { SandboxBadge } from './components/SandboxBadge'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { scrubEventPii } from '../../shared/sentryScrub'

// Renderer-side crash reporting — same init as the main entry (main.tsx). No-op
// without a DSN (dev builds).
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    beforeSend: (event) => scrubEventPii(event)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary label="insight-toast-root" fallback={null}>
      <HashRouter>
        <InsightToast />
      </HashRouter>
    </ErrorBoundary>
    <SandboxBadge />
  </StrictMode>
)
