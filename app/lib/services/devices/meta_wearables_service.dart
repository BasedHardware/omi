import 'dart:async';

import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';

enum MetaGlassesCameraPermissionState {
  notRegistered,
  unavailable,
  needsRequest,
  requesting,
  granted,
}

class MetaWearablesSnapshot {
  final RegistrationState registrationState;
  final List<DeviceInfo> devices;
  final DeviceInfo? activeDevice;
  final MetaGlassesCameraPermissionState cameraPermissionState;
  final Map<String, Object?> diagnostics;

  const MetaWearablesSnapshot({
    required this.registrationState,
    required this.devices,
    required this.activeDevice,
    required this.cameraPermissionState,
    required this.diagnostics,
  });

  bool get cameraPermissionGranted => cameraPermissionState == MetaGlassesCameraPermissionState.granted;

  bool get readyForRecording =>
      registrationState == RegistrationState.registered && activeDevice != null && cameraPermissionGranted;
}

class MetaWearablesService {
  const MetaWearablesService();

  Stream<RegistrationState> registrationStateStream() => MetaWearablesDat.registrationStateStream();

  Stream<DeviceInfo?> activeDeviceStream() => MetaWearablesDat.activeDeviceStream();

  Stream<List<DeviceInfo>> devicesStream() => MetaWearablesDat.devicesStream();

  Future<MetaWearablesSnapshot> snapshot() async {
    final registrationState = await MetaWearablesDat.getRegistrationState();
    final devices = await MetaWearablesDat.getDevices();
    final activeDevice = await _activeDeviceSnapshot(devices);
    final cameraPermissionState = await _cameraPermissionSnapshot(registrationState, devices, activeDevice);
    final diagnostics = await MetaWearablesDat.dumpDiagnostics();

    return MetaWearablesSnapshot(
      registrationState: registrationState,
      devices: devices,
      activeDevice: activeDevice,
      cameraPermissionState: cameraPermissionState,
      diagnostics: diagnostics,
    );
  }

  Future<BtDevice> startPairing() async {
    await MetaWearablesDat.requestAndroidPermissions();
    await MetaWearablesDat.startRegistration();
    final snapshot = await this.snapshot();
    return toBtDevice(
      snapshot.activeDevice ??
          (snapshot.devices.isNotEmpty
              ? snapshot.devices.first
              : const DeviceInfo(uuid: 'meta-registration-pending', name: 'Meta Wearables', kind: DeviceKind.unknown)),
    );
  }

  Future<bool> requestCameraPermission() => MetaWearablesDat.requestCameraPermission();

  Future<void> disconnect() => MetaWearablesDat.stopStreamSession();

  Future<void> forgetLocalRegistration() => MetaWearablesDat.startUnregistration();

  Future<int> startPreviewStream({String? deviceUUID, int fps = 30, StreamQuality quality = StreamQuality.medium}) =>
      MetaWearablesDat.startStreamSession(deviceUUID: deviceUUID, fps: fps, quality: quality);

  Future<void> stopPreviewStream({String? deviceUUID}) => MetaWearablesDat.stopStreamSession(deviceUUID: deviceUUID);

  /// Native-pushed per-frame stream. Used as the background-capable capture
  /// trigger (event delivery keeps working while backgrounded via
  /// enableBackgroundStreaming, unlike a Dart timer which suspends).
  Stream<VideoFrame> videoFrames() => MetaWearablesDat.videoFramesStream();

  Future<void> openFirmwareUpdate() => MetaWearablesDat.openFirmwareUpdate();

  Future<void> openDATGlassesAppUpdate() => MetaWearablesDat.openDATGlassesAppUpdate();

  Future<DeviceInfo?> _activeDeviceSnapshot(List<DeviceInfo> devices) async {
    try {
      return await MetaWearablesDat.activeDeviceStream().first.timeout(const Duration(milliseconds: 500));
    } on TimeoutException {
      return null;
    }
  }

  Future<MetaGlassesCameraPermissionState> _cameraPermissionSnapshot(
    RegistrationState registrationState,
    List<DeviceInfo> devices,
    DeviceInfo? activeDevice,
  ) async {
    if (registrationState != RegistrationState.registered) {
      return MetaGlassesCameraPermissionState.notRegistered;
    }
    if (activeDevice == null && devices.isEmpty) {
      return MetaGlassesCameraPermissionState.unavailable;
    }
    try {
      final granted = await MetaWearablesDat.getCameraPermissionStatus();
      return granted ? MetaGlassesCameraPermissionState.granted : MetaGlassesCameraPermissionState.needsRequest;
    } catch (_) {
      return MetaGlassesCameraPermissionState.unavailable;
    }
  }

  BtDevice toBtDevice(DeviceInfo device) {
    return BtDevice(
      id: device.uuid,
      name: device.name.isNotEmpty ? device.name : 'Meta Wearables',
      type: DeviceType.metaWearables,
      rssi: 0,
      modelNumber: device.kind.name,
      firmwareRevision: 'Unknown',
      hardwareRevision: 'Meta Wearables DAT',
      manufacturerName: 'Meta',
    );
  }
}
