# Frame processing

Two ways to grab still imagery from a running stream.

## `capturePhoto()` — high-resolution still

Triggers the device's actual photo capture path (full sensor
resolution). Available formats: `PhotoFormat.jpeg` (always) and
`PhotoFormat.heic` (iOS, recent Android devices).

```dart
final photo = await MetaWearablesDat.capturePhoto(
  format: PhotoFormat.jpeg,
);
print('Got ${photo.bytes.length} bytes (${photo.format.name})');
```

The returned `format` reflects what the device chose, which can differ
from the requested format on Android.

Notes:

- One capture in flight at a time. Subsequent calls fail with
  `CaptureError(ALREADY_REQUESTING)` until the previous one resolves.
- Captures interleave naturally with the live preview.
- On iOS the capture flows back via the SDK's `photoDataPublisher`; the
  plugin owns a single-slot continuation that resumes on the next
  emitted `PhotoData`.

## `captureStreamFrame(textureId)` — Dart-side snapshot

Pure-Dart RGBA / PNG snapshot of whatever frame is currently rendered
into the Flutter texture. Slow path: allocates a `ui.Image` per call.
Suitable for OCR / ML inference / screenshots at ~2-5 Hz, **not** for
every-frame consumption.

```dart
final frame = await MetaWearablesDat.captureStreamFrame(
  textureId,
  format: FrameFormat.rawRgba,
);
print('Frame: ${frame!.width}x${frame.height}');
```

The plugin caches the latest `VideoStreamSize` from
`videoStreamSizeStream`; you don't need to pass dimensions explicitly.
Falls back to 1280x720 if no size has been observed yet.

## `videoFramesStream()` — every frame

Broadcast stream of every decoded video frame produced by the active
stream session. Payload is a [`VideoFrame`](../lib/src/models/video_frame.dart)
with platform-defined raw bytes:

| Platform | `codec` | Format                                           |
| -------- | ------- | ------------------------------------------------ |
| iOS      | `raw`   | BGRA (`bytesPerRow * height` bytes)              |
| Android  | `raw`   | I420 (`width * height * 3/2` bytes, tightly packed) |
| iOS      | `hvc1`  | HEVC NAL bytes, VPS/SPS/PPS prepended on keyframes (Slice G) |
| Android  | `hvc1`  | HEVC NAL bytes (Slice G — texture preview disabled) |

```dart
final sub = MetaWearablesDat.videoFramesStream().listen((frame) {
  print('Frame ${frame.width}x${frame.height} '
      '${frame.bytes.length} bytes pts=${frame.ptsUs}us');
});
// Remember to cancel when you no longer need every frame; payloads are
// large and the native side only copies when at least one subscriber is
// attached.
await sub.cancel();
```

### Budget

- Raw BGRA at 720p is ≈3.7 MB per frame; at 30 fps that's ≈110 MB/s
  through the platform channel. Subscribe for as little of the session
  as possible.
- I420 at 720p is ≈1.3 MB per frame (~40 MB/s at 30 fps).
- The plugin gates the per-frame copy on subscriber presence — if no
  Dart listener is attached, the native side skips serialisation
  entirely. The texture preview path stays cheap regardless of
  subscriber count.
- For longer recordings, write the frames to disk inside the listener
  (e.g. `RandomAccessFile.write`) rather than buffering them in memory.

## Choosing between the three

| Need                           | Use                  |
| ------------------------------ | -------------------- |
| Highest possible resolution    | `capturePhoto`       |
| Saving photos to gallery       | `capturePhoto`       |
| OCR / ML on live frames        | `captureStreamFrame` |
| Single-frame screenshot of UI  | `captureStreamFrame` |
| Record / process every frame   | `videoFramesStream`  |
