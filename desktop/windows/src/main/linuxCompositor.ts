// Wlroots-family compositors known to ship without reliable XWayland support
// (confirmed on niri — see AGENTS.md's Linux dev section: the XWayland ozone
// path can fail to map the main window at all there, tray icon only). Sway
// and Hyprland are the other two wlroots compositors this project's docs call
// out (docs/linux-screen-recording.md) and share the same "XWayland is
// optional, sometimes absent" shape, so they're treated the same pending
// their own confirmed repro. Detected via each compositor's own session
// marker env var — XDG_CURRENT_DESKTOP isn't set consistently across them.
const WAYLAND_NATIVE_COMPOSITORS: Record<string, string> = {
  niri: 'NIRI_SOCKET',
  sway: 'SWAYSOCK',
  hyprland: 'HYPRLAND_INSTANCE_SIGNATURE'
}

export function detectLinuxCompositor(): string | undefined {
  for (const [name, marker] of Object.entries(WAYLAND_NATIVE_COMPOSITORS)) {
    if (process.env[marker]) return name
  }
  return undefined
}

// XWayland (ozone-platform=x11) is the default because it's the only path
// with working global shortcuts (push-to-talk/overlay summon) and the X11
// active-window query — see index.ts. That default only holds up on
// compositors that actually provide XWayland; on ones that don't, it leaves
// the main window unmapped instead of just degraded, so native Wayland (with
// its own, lesser limitations) is the better default there. OMI_OZONE stays
// available as an explicit override in either direction.
export function defaultOzonePlatform(): 'wayland' | 'x11' {
  if (process.env.XDG_SESSION_TYPE !== 'wayland') return 'x11'
  return detectLinuxCompositor() ? 'wayland' : 'x11'
}
