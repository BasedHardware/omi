// Slim renderer entry for the halo window (#/glow). It mounts ONLY the
// GlowWindow component tree — not the full app (MainViews, three.js orb,
// onnxruntime VAD, all pages). Every aux window used to load index.html's full
// SPA (~200 MB RSS each); this entry loads a fraction. See glow.html and
// perf/win-slim-aux-windows.
//
// The ancestor tree mirrors what GlowWindow had inside App.tsx today
// (StrictMode > ErrorBoundary[fallback=null for overlay windows] > HashRouter),
// plus the dev-only SandboxBadge sibling — so nothing the window renders changes.
import './styles/globals.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/electron/renderer'
import { HashRouter } from 'react-router-dom'
import { GlowWindow } from './components/glow/GlowWindow'
import { SandboxBadge } from './components/SandboxBadge'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { scrubEventPii } from '../../shared/sentryScrub'

// Renderer-side crash reporting — same init as the main entry (main.tsx), so
// overlay-window crashes are still reported. No-op without a DSN (dev builds).
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    beforeSend: (event) => scrubEventPii(event)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary label="glow-root" fallback={null}>
      <HashRouter>
        <GlowWindow />
      </HashRouter>
    </ErrorBoundary>
    <SandboxBadge />
  </StrictMode>
)
