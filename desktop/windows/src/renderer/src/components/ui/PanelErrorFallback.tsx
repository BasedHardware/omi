import { Button } from './Button'

// Per-panel fallback for the content-area boundaries in MainViews. One page's
// render throw degrades to this small card while the sidebar/shell and the other
// (mounted-hidden) panels stay alive — the opposite of the whole-window blank the
// root boundary catches. It fills its panel slot rather than the window. A failed
// boundary stays failed until it remounts, so a reload is the one in-app recovery;
// the button offers it. Neutral/white accent only — no purple (INV-UI-1).
export function PanelErrorFallback(): React.JSX.Element {
  return (
    <div className="flex h-full min-h-0 flex-col items-center justify-center p-6 text-center">
      <div className="w-full max-w-sm rounded-[var(--radius-card)] border border-white/[0.08] bg-[var(--bg-secondary)] p-6">
        <div className="text-sm font-medium text-white/95">This page couldn&apos;t load</div>
        <div className="mt-1.5 text-xs leading-relaxed text-white/60">
          Something went wrong while opening it. Reload Omi, or try another page.
        </div>
        <div className="mt-4 flex justify-center">
          <Button size="sm" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      </div>
    </div>
  )
}
