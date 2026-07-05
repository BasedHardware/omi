# Streaming

Live preview from the glasses' camera renders into a Flutter `Texture`
widget. Frames are delivered zero-copy on iOS (CVPixelBuffer) and
CPU-decoded I420 -> ARGB on Android (Surface backed by a
`SurfaceTexture`).

## Prerequisites

1. Registration is complete (`RegistrationState.registered`).
2. The user has granted camera permission via
   `requestCameraPermission()`.

## Minimal example

```dart
final id = await MetaWearablesDat.startStreamSession(
  fps: 30,
  quality: StreamQuality.high,
);

return AspectRatio(
  aspectRatio: 720 / 1280,
  child: Texture(textureId: id),
);
```

## Reacting to lifecycle events

Three EventChannels report what the SDK is doing:

```dart
MetaWearablesDat.streamSessionStateStream().listen((s) {
  print('Session: $s'); // streaming / paused / ...
});
MetaWearablesDat.streamSessionErrorStream().listen((e) {
  print('Session error: $e');
});
MetaWearablesDat.videoStreamSizeStream().listen((s) {
  print('Now ${s.width}x${s.height}');
});
```

## Pause / resume

In v0.1.0 `pauseStreamSession` / `resumeStreamSession` are documented
no-ops on both platforms. The Meta SDK drives pause from the device
itself (hinges closed, thermal throttling). The methods exist so host
apps can call them unconditionally; the actual transition arrives via
`sessionStateStream`.

## Stopping

```dart
await MetaWearablesDat.stopStreamSession();
```

This releases the texture, tears down the underlying session, and
cancels frame collection. Call it from the screen's `dispose()` to
avoid leaking resources.

## Codec selection (`videoCodec`)

`startStreamSession` accepts a `videoCodec: VideoCodec` parameter
defaulting to `VideoCodec.raw`. The codec drives both the wire payload
on `videoFramesStream()` and (on iOS) whether the texture preview is
decoded via VideoToolbox:

| Codec | iOS preview | iOS frames               | Android preview | Android frames                 |
| ----- | ----------- | ------------------------ | --------------- | ------------------------------ |
| `raw`  | BGRA texture | BGRA bytes (`bytesPerRow`) | I420 texture     | I420 bytes (`bytesPerRow=null`) |
| `hvc1` | BGRA texture (VTDecompressionSession) | HEVC NAL bytes, VPS/SPS/PPS prepended on keyframes | (disabled, see below) | HEVC NAL bytes |

```dart
final id = await MetaWearablesDat.startStreamSession(
  fps: 30,
  quality: StreamQuality.high,
  videoCodec: VideoCodec.hvc1,
);
```

### `hvc1` on Android

Android's `Texture(textureId:)` widget is **not** populated when
`videoCodec == hvc1`. Surfacing the compressed bytes into a preview
requires a `MediaCodec` decoder which the plugin does not own — host
apps that need both a preview and a compressed wire format should keep
the default `raw` codec and run their own HEVC encoder on top of
`videoFramesStream` if they want compressed output.

Bytes-per-second drops roughly 70-90% vs `raw` on both platforms, which
makes `hvc1` the right choice for long-running recording or remote
streaming pipelines.

## Performance notes

- Android CPU-decodes I420 on the plugin's worker scope. At 720p@30fps
  this is ~5-15% of one core on every device that meets `minSdk = 31`.
  GPU-accelerated rendering ships in v0.2.
- iOS hands the platform-decoded `CVPixelBuffer` directly to Flutter's
  texture registry, no copy.
- The plugin retains only the latest frame; if Flutter falls behind on
  rasterisation, frames are simply dropped, which is exactly what you
  want for a live preview.
