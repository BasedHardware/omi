# Omi for Linux - Port Plan

Goal: a Linux desktop build of Omi that stays as close as possible to the Windows
app (`desktop/Windows`) and the macOS Swift app (`desktop/Desktop`), talking to the
same production backends, with as many features working as a Linux build can support.

## Approach

This is the same Electron + TypeScript + React app as the Windows port. The whole
renderer, the shared types, the preload bridge, and most of the main process are
platform-agnostic and are reused unchanged, so the UI is identical to the Windows
app screen for screen. The port is confined to the few main-process modules that
touch Windows-only APIs, plus the packaging config.

## Reused unchanged

- All of `src/renderer` (every page, the floating bar, the theme tokens in
  `theme.css`, the PCM audio worklet). This is what holds design parity at the
  same level as the Windows app.
- `src/shared`, `src/preload`.
- Cross-platform main modules: apiProxy, transcription, realtime, auth, secrets,
  byok, ipc, fileIndex, env, the rewind dHash and SQLite store, the proactive and
  focus engines.

## What changes for Linux

| Area | Windows | Linux |
|---|---|---|
| System audio loopback | WASAPI loopback via `setDisplayMediaRequestHandler` `audio: 'loopback'` | PulseAudio/PipeWire monitor source; falls back to mic-only if no monitor is available |
| Screen capture | desktopCapturer (DXGI) | desktopCapturer; works on X11 directly, Wayland via the xdg-desktop-portal PipeWire path |
| OCR (Rewind) | Windows.Media.Ocr PowerShell sidecar | Tesseract CLI sidecar (`resources/ocr-worker.cjs` under Electron-as-Node); same one-path-per-line JSON protocol |
| Secret storage | safeStorage (DPAPI) | safeStorage (libsecret, GNOME Keyring or KWallet); same fail-closed behavior, degrades clearly if no keyring |
| Launch at login | `app.setLoginItemSettings` | freedesktop autostart file under the resolved XDG config directory |
| Global hotkey | globalShortcut | globalShortcut; works on X11, restricted on Wayland |
| Tray | Electron Tray | Electron Tray via AppIndicator; right-click context menu, icon from `resources/tray_icon.png` |
| Floating bar / glow overlay | frameless always-on-top, click-through | same, X11 always-on-top and click-through; positioning is X11-first, Wayland-limited |
| Protocol (`omi-computer://`) | registry scheme | `setAsDefaultProtocolClient` plus a `.desktop` `MimeType x-scheme-handler/omi-computer`; the callback URL arrives on the second-instance argv |
| Auto-update | electron-updater (NSIS) | electron-updater (AppImage) |
| Packaging | NSIS installer + portable exe | electron-builder AppImage (portable analog) plus `.deb` |

## Backends (same as Windows and Mac)

No backend changes. Same `api.omi.me` Python backend, the same Cloud Run Rust
desktop backend, the same Firebase auth. `OMI_PYTHON_API_URL` and
`OMI_DESKTOP_API_URL` overrides still apply.

## Build and run

Requires Node 20+, a Linux desktop (X11 for the first cut), and `tesseract-ocr`
installed for Rewind OCR.

```bash
cd desktop/Linux
npm install
npm run dev
npm run dist   # AppImage + .deb in dist/
```

The `.deb` declares `tesseract-ocr` and `libsecret-1-0` as dependencies. The
AppImage checks for tesseract at runtime and disables OCR cleanly if it is missing.

## Risks and mitigations

- System-audio loopback is the main risk. Chromium loopback audio through
  getDisplayMedia is not reliable on Linux, so live conversation capture uses the
  PulseAudio/PipeWire monitor source where present and degrades to microphone-only
  otherwise. Screenshots and push-to-talk are unaffected.
- Wayland restricts global shortcuts, always-on-top, and window positioning. The
  first cut targets X11; Wayland still works for the main window and for capture
  through the portal, with the floating bar and hotkey degraded.
- better-sqlite3 needs a Linux prebuild or a rebuild against the Electron ABI;
  `electron-builder install-app-deps` handles that.
