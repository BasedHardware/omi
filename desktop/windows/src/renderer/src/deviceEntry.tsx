// Slim renderer entry for the hidden device window (#/device). It mounts ONLY
// the wearable host tree — WebBluetooth transport, BLE audio decode, and the
// listen lane — not the app UI graph. The device stack lives in a renderer at
// all because Chromium exposes navigator.bluetooth only to renderers, and it
// lives in a HIDDEN one so a paired wearable keeps streaming with every UI
// window closed. See device.html and main/deviceWindow.ts.
import './styles/globals.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/electron/renderer'
import { HashRouter } from 'react-router-dom'
import { DeviceApp } from './device/DeviceApp'
import { SandboxBadge } from './components/SandboxBadge'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { scrubEventPii } from '../../shared/sentryScrub'

// Renderer-side crash reporting — same init as the capture entry. No-op without
// a DSN (dev builds).
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    beforeSend: (event) => scrubEventPii(event)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary label="device-root" fallback={null}>
      <HashRouter>
        <DeviceApp />
      </HashRouter>
    </ErrorBoundary>
    <SandboxBadge />
  </StrictMode>
)
