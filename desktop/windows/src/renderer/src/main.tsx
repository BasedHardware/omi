// App-wide typeface: Inter Variable with optical sizing (bundled, OFL). See
// globals.css --font-app for the stack + the Phase 8 font decision notes.
import '@fontsource-variable/inter/opsz.css'
// Italic instances are REQUIRED because globals.css sets `font-synthesis: none`
// (no faux-slant): without the real italic faces, every <em>/`.italic` would
// render upright. Roman + italic together satisfy the charter's no-synthesis rule.
import '@fontsource-variable/inter/opsz-italic.css'
// Code/monospace typeface: JetBrains Mono Variable (bundled, OFL) — the
// deterministic monospace behind --font-code / the `font-mono` utility (code
// blocks, transcripts, agent output). See globals.css --font-code.
import '@fontsource-variable/jetbrains-mono'
// Real code italics (same font-synthesis:none rationale as Inter above).
import '@fontsource-variable/jetbrains-mono/wght-italic.css'
// Serif ACCENT typeface: Newsreader Variable (bundled, OFL) — the New York analog
// behind --font-serif / the `font-serif` utility. The Hub uses it for stat-ribbon
// numerals, Connect column headers, and the "Try asking" headline; nothing else.
// Roman only: the serif never renders italic copy, so the italic faces would be
// dead weight in the bundle (font-synthesis:none only bites where italics are used).
import '@fontsource-variable/newsreader/opsz.css'
import './styles/globals.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/electron/renderer'
import App from './App'
import { SandboxBadge } from './components/SandboxBadge'
import { scrubEventPii } from '../../shared/sentryScrub'
import { isSecondaryWindow } from './lib/windowRole'
import { initFontScale } from './lib/fontScale'

// Renderer-side crash reporting. Only initializes when a DSN is configured, so
// dev builds (and any build without the env var) stay entirely offline. Emails
// are scrubbed from event text before send as a best-effort PII guard.
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    beforeSend: (event) => scrubEventPii(event)
  })
}

// Startup-phase marks are the MAIN window's cost. Secondary windows (overlay,
// insight-toast, hidden capture) share this bundle and would otherwise fire the
// same marks and race the bench — the capture window in particular first-paints
// almost immediately. Gate every perf mark on being the primary window.
const IS_PRIMARY_WINDOW = !isSecondaryWindow()

// Startup-phase mark: all module imports above are now evaluated (including the
// App graph, which dynamically — not statically — pulls in @huggingface/
// transformers). Splits the startup headline into "bundle download + eval" vs
// "render + first paint".
if (IS_PRIMARY_WINDOW) window.omi?.perfMark('renderer:eval')

// Apply the persisted UI font scale and register the Ctrl+font shortcuts before
// first render — main window only (secondary windows are visually exempt).
if (IS_PRIMARY_WINDOW) initFontScale()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <SandboxBadge />
  </StrictMode>
)

// Report the first painted frame to the main process for the startup benchmark.
// Two rAFs: the first fires before paint, the second after the first frame is on
// screen.
if (IS_PRIMARY_WINDOW) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => window.omi?.perfFirstPaint())
  })
}
