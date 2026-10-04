# Multi-device capture (Omi + OmiGlass together)

Linked from `app/AGENTS.md`. How the Flutter app keeps an Omi pendant and an
OmiGlass connected at the same time and feeds both into one conversation.

## Connections

- `DeviceService` (`app/lib/services/devices.dart`) holds one `DeviceConnection`
  per device id. `ensureConnection(id)` never disconnects another device;
  `disconnectDevice(id)` and `forgetDevice(id)` are per device. A per-device
  mutex lets an out-of-range pendant hit its 60 s connect timeout without
  holding up the glasses next to the phone.
- The connection factory is injectable (`DeviceService(connectionFactory: …)`);
  `app/test/services/devices/device_service_multi_connection_test.dart` drives it
  with in-memory transports.
- Native (`OmiBleManager.swift`, `OmiBleManager.kt`) and `BleBridge` were
  already keyed per peripheral; nothing native changed.

## Saved devices

- Two prefs slots: `btDevice` (primary) and `companionBtDevice`.
  `pairedDeviceIds` is the auto-connect set `DeviceProvider.initiateConnection`
  walks (attempts run in parallel).
- Slots are storage, not roles. `forgetSavedBtDevice(id)` drops a device from
  every slot and promotes the companion when the primary is forgotten.
  `DeviceProvider.forgetDevice(id)` is the single owner of unpairing (prefs,
  connection, transport, native `unmanageDevice`, role reconciliation); both
  unpair UIs call it.
- `BtDevice.getDeviceInfo(null)` looks up the saved copy of the asking device by
  id (not the primary slot), so a glasses-only session never inherits pendant
  metadata.

## Roles

`DevicePairingRoles` (`app/lib/services/devices/device_pairing_roles.dart`) is
pure and unit-tested:

| Connected | Audio | Photos |
|---|---|---|
| Omi only | Omi | — |
| OmiGlass only | OmiGlass | OmiGlass |
| Omi + OmiGlass | Omi | OmiGlass |

- `isCameraDevice` is the one home for the "openglass type or glass-named omi"
  heuristic; `FirmwareUpdateBuildPolicy.isOpenGlassDevice` and
  `DeviceConnectionFactory` delegate to it.
- `canPairAsCompanion(primary, candidate)`: exactly one camera device, the
  pendant is `DeviceType.omi`. Same-kind devices keep replacing each other.
- `DeviceProvider` tracks every connected device and runs `_reconcileRoles`
  (serialized) on each connect/disconnect. The audio device goes through the
  existing single-device paths (`_onDeviceConnected` / `onDeviceDisconnected`,
  so battery, firmware checks, WAL syncs and `connectedDevice` keep their
  meaning). The camera device becomes `companionDevice` (own battery listener)
  and is handed to `CaptureController.updatePhotoDevice`.
- If the pendant drops, the glasses take over audio (they have a mic); when the
  pendant returns they go back to photos.

## Capture

- `CaptureController.photoDevice` = companion camera, else the recording device.
  `_initiateDevicePhotoStreaming` starts the camera on that device;
  `_photoStreamDeviceId` remembers which camera was started so
  `_stopDevicePhotoStreaming` stops the right one after roles change.
- Photos ride the audio session's `/v4/listen` socket as `image_chunk` frames,
  so no backend change: `resolve_photo_conversation_source` relabels the
  conversation `openglass` on the first photo.
- Pause/mute affects audio only (unchanged from the single-device OmiGlass
  behaviour).

## UI

- `ConnectedDevice` page: "Second device" card (status + battery, forget) or
  "Pair a second device" (opens `ConnectDevicePage`). The picker calls
  `DeviceProvider.startDiscoveryScanning` so nearby devices show up while a
  device is already paired, and stops it on dispose.
- Home battery pill shows the companion icon and battery next to the primary.
- Pairing goes through `OnboardingProvider.handleTap`: companion when
  `canPairAsCompanion`, otherwise the replace flow (which also drops a
  companion that no longer pairs with the new primary).
