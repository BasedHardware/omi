// The main window hides the native title bar (titleBarStyle: 'hidden') and
// keeps native caption buttons via the Window Controls Overlay — so Snap
// Layouts hover, minimize/maximize/close all stay OS-native. This strip is
// the drag surface that replaces the title bar. Double-click-to-maximize is
// handled natively by the app-region.
//
// `block` reserves real layout height (the app shell's top row);
// `overlay` floats over full-bleed screens (login/onboarding) whose content
// is centered well clear of the strip.
export function TitleBar({
  variant = 'block',
  onHome = false
}: {
  variant?: 'block' | 'overlay'
  // The authed shell's block strip sits directly above the active route. On Home
  // the route paints a DARKER "stage" (bg-home-paper #050505 + glow/vignette) that
  // stops below this strip, so a transparent strip reads as a visibly lighter band
  // (the app base --bg-primary #0f0f0f) floating over the near-black stage. Every
  // other route uses --bg-primary as its own canvas, so the transparent strip
  // already blends there. When set, paint the strip with the home paper so it
  // reads as the same near-black surface as the stage below — faithful to Mac,
  // where the stage is full window height and the caption region sits over it
  // (DashboardPage HomeCanvasBackground). Only the shell passes this (on Home);
  // the overlay variant (login/onboarding) never does, so its full-bleed screens
  // keep a transparent strip.
  onHome?: boolean
}): React.JSX.Element {
  const seamlessHome = variant === 'block' && onHome
  return (
    <div
      aria-hidden
      className={
        variant === 'block' ? 'h-9 w-full shrink-0' : 'fixed inset-x-0 top-0 z-[90] h-9'
      }
      style={
        {
          WebkitAppRegion: 'drag',
          ...(seamlessHome ? { background: 'var(--home-paper)' } : null)
        } as React.CSSProperties
      }
    />
  )
}
