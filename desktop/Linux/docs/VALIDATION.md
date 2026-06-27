# Linux Desktop Validation

Run these from a Linux host with Node 20+, a working desktop session, and
Tesseract installed if Rewind OCR is being checked.

```bash
cd desktop/Linux
npm install
npm run typecheck
npm run build
npm run dist:appimage
npm run dist:deb
```

Smoke-test checklist before a release candidate:

- Start the unpacked build or AppImage and confirm Google or Apple auth returns
  through the `omi-computer://` callback.
- Confirm authenticated REST calls send `X-App-Platform: linux` and that the
  backend records Linux as desktop platform activity.
- Start a push-to-talk recording and a live conversation. On hosts without a
  PulseAudio or PipeWire monitor source, confirm live conversation falls back to
  microphone-only without crashing.
- Capture "What do you see?" once on X11 and once on Wayland, if available.
- Open Rewind, confirm Tesseract OCR indexes new frames, then search for text
  visible on screen.
- Use the tray and Settings update action. It should resolve as a no-op while
  Linux auto-update is disabled.
- Package both AppImage and `.deb`; install the `.deb` in a clean VM and confirm
  `tesseract-ocr`, `libsecret-1-0`, `libnotify4`, and `libxss1` are pulled in.
