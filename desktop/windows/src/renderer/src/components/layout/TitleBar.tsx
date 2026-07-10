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
  variant = 'block'
}: {
  variant?: 'block' | 'overlay'
}): React.JSX.Element {
  return (
    <div
      aria-hidden
      className={
        variant === 'block' ? 'h-9 w-full shrink-0' : 'fixed inset-x-0 top-0 z-[90] h-9'
      }
      style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
    />
  )
}
