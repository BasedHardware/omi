import { Button } from './Button'

// Root-level fallback for the app-wide <ErrorBoundary> in main.tsx. Without it, a
// render-time throw anywhere below <App /> unmounts the whole React tree to a blank
// window for the rest of the session — and because the renderer process stays
// alive, the main-process auto-reload safety nets never fire. This paints an
// honest, self-contained recovery surface instead.
//
// Deliberately calm and neutral, matching DbRecoveryNotice's tone: a reload almost
// always clears a transient render error. It paints its OWN opaque background from
// the app tokens (--bg-primary) so it stays legible even when the shell that
// normally draws the window is the thing that just crashed. Neutral/white accent
// only — no purple (INV-UI-1).
export function AppCrashScreen(): React.JSX.Element {
  return (
    <div
      role="alert"
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-[var(--bg-primary)] p-6"
    >
      <div className="w-full max-w-sm rounded-[var(--radius-card)] border border-white/[0.08] bg-[var(--bg-secondary)] p-6 text-center shadow-[0_1px_3px_rgba(0,0,0,0.3)]">
        <div className="text-base font-medium text-white/95">Something went wrong</div>
        <div className="mt-1.5 text-sm leading-relaxed text-white/60">
          Omi ran into an unexpected error. Reloading usually fixes it.
        </div>
        <div className="mt-5 flex justify-center">
          {/* location.reload() recovers this window and is lighter than a full app
              relaunch — the right primary action for a transient render throw. */}
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </div>
      </div>
    </div>
  )
}
