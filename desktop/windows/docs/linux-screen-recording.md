# Linux screen recording (Rewind) troubleshooting

Rewind needs `desktopCapturer.getSources()` to resolve, which on Wayland goes
through the `org.freedesktop.portal.ScreenCast` D-Bus interface. If no portal
backend implements it for the running compositor, Electron fails immediately
(`Failed to get sources.`), Rewind never starts, and — before this doc's
companion fix — nothing told the user why.

## What Omi does automatically

- `RewindCaptureNotice` (`src/renderer/src/components/ui/RewindCaptureNotice.tsx`)
  shows an in-app banner when Rewind is enabled but `desktopCapturer.getSources()`
  failed, with Linux-specific guidance when `process.platform === 'linux'` (see
  `getRewindCaptureDiagnostics` in `src/main/rewind/sourceId.ts`).
- The `.deb` package `Recommends` (not `Depends`) the generic `xdg-desktop-portal`
  front-end (`electron-builder.config.mjs`) — the universal front-end almost every
  desktop already has. It deliberately does **not** depend on a specific backend
  package, because the correct one is compositor-specific (see below) and there is
  no single correct hard dependency across GNOME/KDE/wlroots-family desktops.

## Why this can't be fully automated

A portal **backend** (`xdg-desktop-portal-wlr`/`-gnome`/`-kde`/…) has to run on the
host, register on the system D-Bus session bus, and integrate with whichever
compositor is actually running. That's true regardless of how Omi is packaged —
`.deb`, `AppImage`, or a hypothetical future Flatpak — none of these formats can
bundle or install a working backend themselves:

- **Flatpak** sandboxes the app; it can only *ask* the host's portal dispatcher.
  It cannot bundle a backend — that must already be installed and preferred on
  the host.
- **`.deb`** dependencies resolve once at install time, but the correct backend
  depends on which compositor the user runs, which the package can't know in
  advance.
- **AppImage** has zero ability to install or configure anything system-level.

Mainstream desktop environments (GNOME, KDE) avoid this because their distro
installs *and* preconfigures the matching portal by default. Smaller / newer
wlroots-family compositors (niri, Sway, Hyprland, …) are the common exception —
their distro packaging often ships a portal config that doesn't route
`ScreenCast` anywhere, even when a working backend package is available.

## Fixing it on a wlroots-family compositor (niri, Sway, Hyprland, …)

Confirmed live on Fedora Asahi Remix + niri, where `niri-portals.conf` shipped
with no `ScreenCast` route at all:

1. Install the wlr portal backend:
   ```
   sudo dnf install xdg-desktop-portal-wlr   # Fedora
   sudo apt install xdg-desktop-portal-wlr   # Debian/Ubuntu
   ```
2. Add a user-level override (safer than editing the system file, which a
   package update can overwrite) at
   `~/.config/xdg-desktop-portal/<compositor>-portals.conf` (e.g.
   `niri-portals.conf`):
   ```ini
   [preferred]
   default=gnome;gtk;
   org.freedesktop.impl.portal.ScreenCast=wlr
   org.freedesktop.impl.portal.Screenshot=wlr
   ```
3. Restart the portal so it picks up both the new backend and the config:
   ```
   systemctl --user restart xdg-desktop-portal
   ```
   (a full logout/login also works if that doesn't take effect)
4. Restart Omi. `getRewindCaptureSourceId()`'s screen-source lookup is cached
   for the whole process lifetime (`src/main/rewind/sourceId.ts` — deliberately,
   `desktopCapturer.getSources()` is slow), so a running instance won't pick up
   a newly-fixed portal without a restart.

## What to expect on first launch after the fix

The portal's interactive picker for a wlroots-family compositor isn't a dialog
window — it's a compositor-driven interactive selection (a changed cursor to
click a window, or click-drag a region), similar to a screenshot tool. Select
once; the grant is then cached for the process lifetime, so later Rewind
toggles won't show it again — that's expected, not a regression.

## Diagnosing on your own machine

```
wpctl status                     # confirm PipeWire even has an audio Source (mic issues)
busctl --user list | grep portal # confirm a backend (org.freedesktop.impl.portal.desktop.*) is registered
```
If no `org.freedesktop.impl.portal.desktop.<backend>` line appears for your
compositor's expected backend, the backend isn't installed, running, or
D-Bus-activatable — start from step 1 above.
