# Omi on Linux

Status: **MVP + screen-reading working** — builds, the full test suite passes
(reproduce with `cd desktop/windows && npm test`), launches and renders on X11,
app-usage tracking works, and **screen OCR ("what's on my screen") works** via a
Tesseract-backed helper.

Architecture choice: Linux is a **platform seam on `desktop/windows`**, not a
forked `desktop/linux` / `desktop/Linux` tree. Shared renderer/main stay one
codebase; only OS-specific adapters branch on `process.platform`.

## Run from source
```bash
cd desktop/windows
cp .env.example .env          # public Firebase/PostHog config; sign-in works as-is
npm install
npm run dev                   # launch on an X11 session (DISPLAY set)
```

## Runtime dependencies (Debian/Ubuntu)
```bash
sudo apt-get install -y x11-utils tesseract-ocr tesseract-ocr-eng
```
- `x11-utils` provides `xprop` — used for active-window detection (usage-tracking,
  and the OCR helper's window-info op).
- `tesseract-ocr` (+ the `eng` language pack) backs screen OCR. Without it, screen
  reading degrades gracefully (the helper returns an error frame; the rest of the
  app is unaffected).
- Packaged `.deb` already depends on `tesseract-ocr`, `tesseract-ocr-eng`,
  `libnotify4`, and `libxss1`. AppImage users still need the packages above.
- System-audio loopback (meeting capture) needs PulseAudio or `pipewire-pulse`.
  Chromium flag `PulseaudioLoopbackForScreenShare` is enabled on Linux; without
  a Pulse layer the flag is inert and capture falls back to mic-only.
- Headless/CI: run under `xvfb-run` and pass `--no-sandbox`.

## Wayland

The app targets X11. On a Wayland session it defaults to **XWayland**
(`ozone-platform=x11`) because a native Wayland surface breaks Electron global
shortcuts (push-to-talk / overlay summon) and the X11 active-window path. To run
native Wayland anyway, set `OMI_OZONE=wayland` (accepting those limitations).

Screen capture on Wayland goes through the desktop portal, which asks
"Share screen?" for consent — and Electron has no persisted-consent path, so
*continuous* Rewind capture would re-prompt every frame. Therefore, on a Wayland
session, **continuous Rewind capture defaults OFF** (`XDG_SESSION_TYPE=wayland`);
on-demand "what's on my screen" still works (one Share prompt), and you can enable
continuous capture explicitly. X11 sessions keep continuous Rewind on by default.

## What works / what's next
- ✅ Sign-in, mic → cloud transcription, chat, memory (inherited, cross-platform)
- ✅ App-usage tracking (X11 active-window via `linuxForeground.ts`; poll-driven, 15s)
- ✅ Screen OCR / "what's on my screen" (Rewind capture → `omi-ocr-helper` → Tesseract)
- ✅ Wayland sessions via XWayland (shortcuts + active-window work; continuous Rewind
  off by default — see the Wayland section)
- ⏳ Pendant BLE, Glass video, native-Wayland capture (portal restore-token),
  tray/Quit polish, full Windows-parity feature wave (lands with the Windows
  desktop umbrella, then reuses these Linux seams).

## Implementation notes
- `src/main/usage/linuxForeground.ts` — X11 active-window (xprop + /proc/<pid>/exe).
- `src/main/usage/nativeForeground.ts` — Linux branch delegates to the above; the
  Windows (koffi) path is unchanged.
- `src/main/automation/foregroundTargetLogic.ts` — uses `path.win32.basename` so
  exe-path comparison is correct on both Windows and Linux.
- `resources/linux-ocr-helper/omi-ocr-helper` — a Node-script helper that speaks
  the exact `ocr/helperProtocol.ts` stdio frame protocol as `win-ocr-helper.exe`,
  backed by the `tesseract` CLI for OCR and `xprop`/`/proc` for window info.
  `ocr/helperProcess.ts` spawns it with **Electron's bundled Node**
  (`process.execPath` + `ELECTRON_RUN_AS_NODE=1`), so it needs no system `node`
  in packaged AppImage/deb builds.
- `src/main/ocr/resolveHelperPath.ts` — returns the Linux helper path on Linux;
  the Windows path is unchanged. `electron-builder.yml` unpacks `resources/**`,
  so packaged Linux builds ship the helper.
- `electron-builder.yml` — Linux targets are **AppImage + deb** (snap omitted:
  strict confinement blocks `xprop`/`tesseract`/`/proc`).

### Future enhancement
For one-shot "look at my screen now" questions, a vision model (Claude vision, or
the moondream path used by the Glasses) would understand UI/images better than OCR.
OCR is used here for parity with Omi's continuous, local, searchable Rewind model.
