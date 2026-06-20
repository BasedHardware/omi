import './styles/globals.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { SandboxBadge } from './components/SandboxBadge'
import { getPreferences, onPreferencesChange } from './lib/preferences'
import { applyAppScale } from './lib/uiScale'

// Apply the saved UI scale before first paint so the app never flashes at the
// wrong size. The floating-bar window (#/overlay) scales itself (it CSS-zooms a
// fixed-width panel), so the app-level root zoom must NOT run there.
const isOverlayWindow = window.location.hash.startsWith('#/overlay')
if (!isOverlayWindow) {
  applyAppScale(getPreferences().uiScale)
  // Live-update the main window when the scale changes in Settings (same process).
  onPreferencesChange((p) => applyAppScale(p.uiScale))
}

// Startup-phase mark: all module imports above are now evaluated (including the
// App graph, which dynamically — not statically — pulls in @huggingface/
// transformers). Splits the startup headline into "bundle download + eval" vs
// "render + first paint".
window.omi?.perfMark('renderer:eval')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <SandboxBadge />
  </StrictMode>
)

// Report the first painted frame to the main process for the startup benchmark.
// Two rAFs: the first fires before paint, the second after the first frame is on
// screen.
requestAnimationFrame(() => {
  requestAnimationFrame(() => window.omi?.perfFirstPaint())
})
