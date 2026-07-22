// Slim renderer entry for the hidden capture window (#/capture). It mounts ONLY
// the CaptureApp host tree (mic, VAD, PTT, screen, rewind) — not the full app UI
// graph (MainViews, all pages, Hub) or the three.js orb. Every aux window used to
// load index.html's full SPA (~200 MB RSS each); capture still needs onnxruntime
// (VAD), so its bundle stays larger than glow/toast, but it drops the entire
// main-window UI graph and three.js. See capture.html and perf/win-slim-aux-windows.
//
// No fonts / no globals text rendering matter here: the capture window is hidden
// and paints no visible UI. globals.css is still imported so the base reset/vars
// are present (cheap CSS, no heap cost). StrictMode + HashRouter mirror the
// ancestor tree CaptureApp ran under inside App.tsx today, so capture behavior
// (incl. StrictMode effect semantics) is byte-for-byte unchanged.
import './styles/globals.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/electron/renderer'
import { HashRouter } from 'react-router-dom'
import { CaptureApp } from './capture/CaptureApp'
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
    <ErrorBoundary label="capture-root" fallback={null}>
      <HashRouter>
        <CaptureApp />
      </HashRouter>
    </ErrorBoundary>
    <SandboxBadge />
  </StrictMode>
)
