# Omi for Linux

A Linux desktop build of the Omi macOS app (`desktop/Desktop`), sharing the same
codebase as the Windows port (`desktop/Windows`). It looks like the Swift app, talks
to the same production backends, and brings over the same features, with the
platform-specific pieces reimplemented for Linux.

> Stack: Electron 38 + TypeScript + React 18 (electron-vite). It uses the same
> `api.omi.me` Python backend and the same Cloud Run desktop backend the Mac and
> Windows apps use, with the same Firebase auth. Backend changes are limited to
> recognizing `X-App-Platform: linux` as desktop activity. The renderer is
> identical to the Windows app, so the UI matches screen for screen.

## What works

Everything is wired to the same endpoints as the Mac and Windows apps.

- **Sign in** with Google or Apple through the system browser, returning via the
  `omi-computer://` scheme. On Linux the callback URL arrives on the second-instance
  command line and is routed to the same auth handler.
- **Floating control bar**, frameless and always-on-top, with the global hotkey
  (`Ctrl+Shift+Space`, configurable). Works on X11; Wayland restricts always-on-top
  and global shortcuts.
- **Chat** with streaming responses, markdown, session history.
- **"What do you see?"** attaches a screenshot and recent screen OCR to the chat.
- **Push-to-talk voice** and **live conversations** (mic plus system audio). System
  audio uses the PulseAudio/PipeWire monitor source; on a host without one it falls
  back to microphone-only.
- **Conversations, Memories, Tasks, Dashboard, Goals, Graph, Insights** against the
  same REST endpoints.
- **Rewind**: captures the screen, dedupes with a dHash, OCRs each frame with the
  **Tesseract** CLI, indexes the text in SQLite FTS5, and gives you a searchable
  timeline. Everything stays local.
- **Proactive assistant** and **Focus** monitoring, using the same on-device screen
  capture.
- **Apps** (MCP key creation), **Settings**, and a **tray** item. On Linux the tray
  uses AppIndicator, so every action is reachable from the right-click menu.

## Parity with the macOS and Windows apps

The renderer, the shared types, the preload bridge, and most of the main process are
the same files as the Windows port, so the UI and the feature set match. Only the
Windows-coupled main-process modules were reimplemented:

| Area | Windows | Linux |
|---|---|---|
| System audio | WASAPI loopback | PulseAudio/PipeWire monitor source (best-effort, mic fallback) |
| Screen capture | desktopCapturer (DXGI) | desktopCapturer (X11, or Wayland portal) |
| OCR | Windows.Media.Ocr | Tesseract CLI sidecar |
| Secret storage | safeStorage (DPAPI) | safeStorage (libsecret) |
| Launch at login | setLoginItemSettings | `~/.config/autostart/omi.desktop` |
| Tray | Electron Tray | Electron Tray via AppIndicator |
| Protocol callback | registry scheme | `.desktop` MimeType + argv |
| Auto-update | NSIS / electron-updater | Disabled until the official Linux release channel is configured |
| Packaging | NSIS + portable exe | AppImage + .deb |

## Architecture

```
src/
  main/            Electron main process
    index.ts         lifecycle, single instance, omi-computer:// (argv on Linux)
    auth.ts          OAuth + Firebase token store (safeStorage) + refresh
    apiProxy.ts      all HTTP/SSE through main
    transcription.ts WebSocket bridge to /v4/listen and transcribe-stream
    capture.ts       desktopCapturer screenshots + PulseAudio loopback handler
    windows.ts       main window + floating bar geometry
    tray.ts          tray menu (AppIndicator)
    settings.ts      JSON settings + autostart .desktop file
    rewind/          capturer · dhash · ocr (tesseract sidecar) · store (SQLite FTS5)
  preload/         contextBridge -> window.omi
  renderer/        the UI (identical to the Windows app)
  shared/          types shared across processes
resources/
  ocr-worker.cjs   persistent Tesseract OCR sidecar
```

## Build and run

Requires Node 20+, a Linux desktop (X11 for the first cut), and `tesseract-ocr` for
Rewind OCR.

```bash
cd desktop/Linux
npm install
npm run dev        # hot-reload dev
npm run dist       # AppImage + .deb in dist/
```

`npm run dist` produces `dist/Omi-<version>-x86_64.AppImage` and a `.deb`. The `.deb`
declares `tesseract-ocr` and `libsecret-1-0` as dependencies; the AppImage checks for
tesseract at runtime and disables OCR cleanly if it is missing.

### Environment overrides

| Var | Purpose |
|---|---|
| `OMI_PYTHON_API_URL` | override the Python backend (default `https://api.omi.me/`) |
| `OMI_DESKTOP_API_URL` | override the Rust desktop backend |
| `OMI_DEBUG_PORT` | expose Chrome DevTools Protocol for UI automation |
| `OMI_FAKE_AUTH=1` | dev: render the signed-in UI without a real login |

## Notes and limitations

- **Wayland** restricts global shortcuts, always-on-top, and window positioning. The
  first cut targets X11; the main window and screen capture still work on Wayland
  through the portal, with the floating bar and hotkey degraded.
- **System-audio loopback** depends on a PulseAudio or PipeWire monitor source. Where
  there is none, live conversation falls back to microphone-only. Screenshots and
  push-to-talk are unaffected.
- **Auto-update** is intentionally disabled in this PR until maintainers choose
  the official Linux release channel. The `.deb` updates through your package
  manager.
- **Code signing** is not configured; the AppImage is unsigned.
