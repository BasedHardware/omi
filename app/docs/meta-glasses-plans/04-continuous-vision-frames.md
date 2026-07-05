# 04 — Continuous vision via frame stream

## Goal
Move beyond a still every 30s to opt-in continuous visual understanding: tap a
per-frame stream, downsample it, and send frames (or on-device OCR/scene text)
to the backend so the assistant "sees" in near real-time.

> **Heavy feature.** Raw frames are ~3.7 MB each at 720p. This is opt-in, off by
> default, and must be battery/bandwidth-budgeted. Ship the plumbing + a strict
> throttle first; the ML/backend side can follow.

## Grounding (verified)
- Facade: `Stream<VideoFrame> videoFramesStream()`. Native only copies per-frame when a Dart subscriber is attached. `VideoFrame` in `lib/src/models/video_frame.dart`.
- `captureStreamFrame(int textureId, {FrameFormat format})` for pure-Dart single grabs.
- Requires an active stream session (interacts with plan 02 — don't pause between grabs in this mode).

## Steps
1. Add an opt-in mode: extend `MetaGlassesCaptureMode` with `cameraContinuous` OR add a separate bool `continuousVisionEnabled` (persisted pref `metaGlassesContinuousVision`, default false). Prefer a separate bool so it composes with existing modes.
2. Service: add `Stream<VideoFrame> videoFrames()` passthrough.
3. Provider: when continuous vision is on and capturing, subscribe to `videoFrames()`. Apply a hard throttle (e.g. process ≤1 frame/sec via a timestamp gate) and drop frames while a send is in flight (no unbounded buffering — this is NOT the store-and-forward photo queue; live frames are disposable).
4. Downsample before send: reuse/extend `lib/utils/image/image_utils.dart` to scale frames to ≤512px and JPEG-encode; feed through the existing `CaptureController.ingestCapturedImage` path OR a new lighter `image_frame` socket message (decide with backend owner — default to reusing `ingestCapturedImage` with `addToUi: false` to avoid flooding the photo strip).
5. Battery guard: force-disable continuous vision when `health == overheating` (plan 01) and when not on charge if you can detect it; always stop the subscription on `stopCapture`.
6. UI: a toggle on `meta_glasses_page.dart` under the capture-mode selector, with a clear "uses more battery" caption. No purple.
7. l10n: `metaGlassesContinuousVision`, `metaGlassesContinuousVisionCaption` (all locales).

## Tests
- Unit: throttle logic (≤1 frame/sec, drops while in-flight) with a synthetic frame stream.
- Contract test: provider references `videoFramesStream`; the toggle key exists in ARB.

## Acceptance
- Toggling continuous vision on during capture streams downsampled frames at ≤1/sec with bounded memory (no growth over a 5-min run).
- Off by default; disabled automatically on overheat; fully torn down on stop.
- Analyze clean; tests green; l10n 0 untranslated.
