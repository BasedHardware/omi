# 02 — Pause/resume the photo session

## Goal
Stop tearing down and re-creating the camera stream session every 30s. Keep one
session and pause it between stills, resuming just before each capture. Saves
battery and removes the ~1–2s session-start latency (and the "DeviceSession
stopped before reaching .started" failure window) on every photo.

## Grounding (verified)
- Facade has `MetaWearablesDat.pauseStreamSession({String? deviceUUID})` and `resumeStreamSession({String? deviceUUID})`.
- Current loop in `lib/providers/meta_wearables_provider.dart`: `_startPhotoLoop()` opens a low-fps session and a `Timer.periodic(_photoInterval, ...)` calling `_captureGlassesPhoto()`; `_stopPhotoLoop()` calls `stopPreviewStream`.
- `capturePhoto()` requires an *active* (not paused) session, so resume → capture → pause.

## Steps
1. Add service passthroughs in `meta_wearables_service.dart`: `Future<void> pausePreviewStream({String? deviceUUID})` and `resumePreviewStream(...)` wrapping the facade methods.
2. In `MetaWearablesProvider._startPhotoLoop()`: after the first capture, instead of leaving the session running at 5fps continuously, call `pausePreviewStream(deviceUUID: _sessionTargetUuid)`.
3. Change the periodic tick to: `resumePreviewStream` → `await _captureGlassesPhoto()` → `pausePreviewStream`. Guard each with try/catch (a paused/failed resume must fall back to the plan-01 retry, not crash the loop).
4. On `stopCapture()` / `_stopPhotoLoop()`: fully `stopPreviewStream` (not just pause) so the session and texture are released.
5. If `previewTextureId != null` and the live preview is being shown (opt-in), do NOT pause — a visible `Texture` needs the running session. Gate the pause on `previewTextureId == null`.
6. Interaction with plan 01: thermal pause should use `pauseStreamSession` too; don't double-pause (track `_thermalPaused` vs the between-shots pause separately or with one `_sessionPaused` flag).

## Tests
- Unit test (with a fake `MetaWearablesService` recording calls) that a capture tick issues resume→capture→pause in order, and that showing the preview suppresses the between-shot pause.
- Contract test: provider references `pauseStreamSession`/`resumePreviewStream`.

## Acceptance
- With preview off, only one stream session is created per capture run (verify via native log `startStreamSession` count over several minutes — should be ~1, not 1-per-photo).
- Photos still land every ~30s; no regression in the store-and-forward queue or timeline ordering.
- `flutter analyze` clean; tests green.
