# Mock Device Kit

Develop the streaming and capture pipelines without a pair of glasses
on the desk. The plugin wraps Meta's `MockDeviceKit` (iOS:
`MWDATMockDevice`; Android: `mwdat-mockdevice`) so you can pair, power
on, don, and feed simulated devices entirely from Dart.

## Lifecycle

```dart
await MetaWearablesDat.enableMockDevice();
final uuid = await MetaWearablesDat.pairMockRayBanMeta();
await MetaWearablesDat.mockPowerOn(uuid);
await MetaWearablesDat.mockDon(uuid);

// `uuid` now appears in MetaWearablesDat.mockDevicesStream() and is a
// valid `deviceUUID` argument for startStreamSession etc.

// Tear down.
await MetaWearablesDat.unpairMockDevice(uuid);
await MetaWearablesDat.disableMockDevice();
```

## Feeding the mock camera

A mock device's camera is empty by default — `startStreamSession` will
return frames, but they will be black. Set a feed first:

```dart
// Phone's front camera.
await MetaWearablesDat.setMockCameraFacing(uuid, CameraFacing.front);

// Or a video file on disk (mp4 / mov).
await MetaWearablesDat.setMockCameraFeed(uuid, '/storage/.../demo.mp4');

// Or override the photo capture result with a static image.
await MetaWearablesDat.setMockCapturedImage(uuid, '/storage/.../still.jpg');
```

`setMockCameraFacing` and `setMockCameraFeed(filePath)` are mutually
exclusive — the most-recent call wins.

## Watching the paired set

```dart
MetaWearablesDat.mockDevicesStream().listen((devices) {
  print('Now have ${devices.length} mock devices');
});
```

The stream emits the full snapshot every time a device is added or
removed. New subscribers receive the current snapshot immediately.

## Production builds

For v0.1.0 the mock kit ships inside the main plugin. Strip the symbol
in release builds by removing the `mwdat-mockdevice` line from
`android/build.gradle` and the `MWDATMockDevice` product from
`ios/.../Package.swift` until v0.1 ships the dedicated add-on
package (`meta_wearables_dat_flutter_mock`).
