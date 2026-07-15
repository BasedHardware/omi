import { createElement, Suspense } from 'react'
import { getHubConnectContent } from './hubConnectSlot'

// The Connect stage — the slide-down panel the ask bar's "Connect" toggle reveals.
//
// OWNERSHIP: Track 5 owns this CHROME — the bordered panel, its fill/shadow, its
// sizing, and the drop-in transition (via StagePanel in HomeHub). Track 3 owns the
// CONTENT — the source→destination connector tray — and renders it through the slot
// (see hubConnectSlot.ts). Until Track 3 registers content, this shows a resting
// "coming soon" state. When they do, nothing here changes.
//
// SLOT CONTRACT — see hubConnectSlot.ts for the full, authoritative version. In short:
// the content mounts at width:100%/height:100% inside a panel the Hub caps at
// maxWidth 1280 / maxHeight 640 (it flexes to fill the stage, shrinks on short
// windows), the panel itself does NOT scroll (own an internal overflow region), and
// `onDismiss` returns to the resting hub.

// Resting state — shown when no content is registered AND as the Suspense fallback
// while the lazily-imported connections chunk loads on first open.
function RestingState(): React.JSX.Element {
  return (
    <div className="flex flex-1 items-center justify-center">
      <p className="text-[13px] font-medium text-home-muted">Connections are coming soon.</p>
    </div>
  )
}

export function HubConnectPanel({ onDismiss }: { onDismiss: () => void }): React.JSX.Element {
  const content = getHubConnectContent()

  return (
    <div
      className="flex h-full w-full items-stretch justify-center overflow-hidden rounded-[26px] border"
      style={{
        borderColor: 'rgb(var(--home-stage-glow-rgb) / 0.14)',
        backgroundImage:
          'linear-gradient(to bottom, rgb(255 255 255 / 0.03), rgb(var(--home-stage-glow-rgb) / 0.05))',
        boxShadow: '0 18px 44px rgb(0 0 0 / 0.42)'
      }}
      data-testid="hub-connect-panel"
    >
      {content ? (
        // The registered content is a React.lazy component (registered via a dynamic
        // import in connections/register.ts), so it must render under a Suspense
        // boundary. A plain component registered directly (tests) renders fine too.
        <Suspense fallback={<RestingState />}>{createElement(content, { onDismiss })}</Suspense>
      ) : (
        <RestingState />
      )}
    </div>
  )
}
