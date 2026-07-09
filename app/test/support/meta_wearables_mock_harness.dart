import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:omi/services/capture/capture_controller.dart';
// ignore: depend_on_referenced_packages
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

class MetaWearablesMockHarness {
  final platform = RecordingMetaWearablesMockPlatform();

  Future<File> writeFixtureImage(Directory dir) async {
    final file = File('${dir.path}/mock-rayban-frame.png');
    await file.writeAsBytes(fixturePngBytes);
    return file;
  }

  List<DeviceInfo> devicesInTwoLinkStates() => const [
        DeviceInfo(
          uuid: 'mock-rayban-linked',
          name: 'Mock Ray-Ban Linked',
          kind: DeviceKind.rayBanMeta,
          linkState: DeviceLinkState.connected,
        ),
        DeviceInfo(
          uuid: 'mock-rayban-unlinked',
          name: 'Mock Ray-Ban Unlinked',
          kind: DeviceKind.rayBanMeta,
          linkState: DeviceLinkState.disconnected,
        ),
      ];
}

class RecordingCaptureController extends CaptureController {
  final List<Uint8List> ingestedImages = [];
  final List<bool> addToUiValues = [];
  final List<DateTime?> capturedAtValues = [];
  final List<String?> deviceUuidValues = [];
  final List<String?> deviceNameValues = [];
  final List<String?> frameSha256Values = [];
  int streamRecordingCount = 0;
  int stopStreamRecordingCount = 0;

  @override
  Future<void> streamRecording() async {
    streamRecordingCount += 1;
  }

  @override
  Future<void> stopStreamRecording() async {
    stopStreamRecordingCount += 1;
  }

  @override
  Future<bool> ingestCapturedImage(Uint8List imageBytes, {bool addToUi = true, DateTime? capturedAt}) async {
    ingestedImages.add(Uint8List.fromList(imageBytes));
    addToUiValues.add(addToUi);
    capturedAtValues.add(capturedAt);
    return true;
  }

  @override
  Future<bool> cacheCapturedImage(
    Uint8List imageBytes, {
    bool addToUi = true,
    DateTime? capturedAt,
    String? deviceUuid,
    String? deviceName,
    String? frameSha256,
  }) async {
    ingestedImages.add(Uint8List.fromList(imageBytes));
    addToUiValues.add(addToUi);
    capturedAtValues.add(capturedAt);
    deviceUuidValues.add(deviceUuid);
    deviceNameValues.add(deviceName);
    frameSha256Values.add(frameSha256);
    return true;
  }
}

class RecordingMetaWearablesMockPlatform extends MetaWearablesDatPlatform with MockPlatformInterfaceMixin {
  static const uuid = 'mock-rayban-meta-1';
  static const textureId = 771;

  bool enabled = false;
  bool paired = false;
  bool powered = false;
  bool unfolded = false;
  bool donned = false;
  bool cameraGranted = false;
  bool reportsActiveDevice = true;
  bool cameraPermissionStatusThrows = false;
  bool blockCameraPermissionRequest = false;
  bool backgroundStreamingEnabled = false;
  bool emitDeviceChanges = true;
  bool leaveSessionOnFailedStart = false;
  bool streamSessionExists = false;
  int streamStartCallCount = 0;
  int stopStreamSessionCount = 0;
  int failStreamStartCount = 0;
  int frameCaptureCount = 0;
  int cameraPermissionRequestCount = 0;
  String? capturedImagePath;
  String? lastStreamDeviceUuid;
  int? lastStreamFps;
  StreamQuality? lastStreamQuality;
  final StreamController<List<DeviceInfo>> _devicesController = StreamController<List<DeviceInfo>>.broadcast();

  DeviceInfo get device => DeviceInfo(
        uuid: uuid,
        name: 'Mock Ray-Ban Meta',
        kind: DeviceKind.rayBanMeta,
        linkState: powered && unfolded && donned ? DeviceLinkState.connected : DeviceLinkState.disconnected,
      );

  @override
  Future<Map<String, Object?>> dumpDiagnostics() async => {
        'mockDeviceEnabled': enabled,
        'mockDevicePaired': paired,
        'mockCameraGranted': cameraGranted,
      };

  @override
  Future<void> enableMockDevice({bool initiallyRegistered = true, bool initialPermissionsGranted = true}) async {
    enabled = initiallyRegistered;
    cameraGranted = initialPermissionsGranted;
  }

  @override
  Future<void> disableMockDevice() async {
    enabled = false;
    paired = false;
    _emitDevices();
  }

  @override
  Future<String> pairMockRayBanMeta() async {
    paired = true;
    _emitDevices();
    return uuid;
  }

  @override
  Future<List<DeviceInfo>> pairedMockDevices() async => paired ? [device] : [];

  @override
  Future<void> mockPowerOn(String uuid) async {
    powered = true;
    _emitDevices();
  }

  @override
  Future<void> mockPowerOff(String uuid) async {
    powered = false;
    _emitDevices();
  }

  @override
  Future<void> mockUnfold(String uuid) async {
    unfolded = true;
    _emitDevices();
  }

  @override
  Future<void> mockDon(String uuid) async {
    donned = true;
    _emitDevices();
  }

  @override
  Future<void> mockDoff(String uuid) async {
    donned = false;
    _emitDevices();
  }

  @override
  Future<void> setMockPermission(String permission, String status) async {
    if (permission == MockPermission.camera.value) {
      cameraGranted = status == MockPermissionStatus.granted.value;
    }
  }

  @override
  Future<void> setMockCapturedImage(String uuid, String? filePath) async {
    capturedImagePath = filePath;
  }

  @override
  Future<RegistrationState> getRegistrationState() async {
    return enabled ? RegistrationState.registered : RegistrationState.unavailable;
  }

  @override
  Stream<RegistrationState> registrationStateStream() {
    return Stream.value(enabled ? RegistrationState.registered : RegistrationState.unavailable);
  }

  @override
  Future<List<DeviceInfo>> getDevices() async => paired ? [device] : [];

  @override
  Stream<List<DeviceInfo>> devicesStream() async* {
    yield paired ? [device] : [];
    yield* _devicesController.stream;
  }

  @override
  Stream<DeviceInfo?> activeDeviceStream() => Stream.value(paired && reportsActiveDevice ? device : null);

  void _emitDevices() {
    if (emitDeviceChanges && !_devicesController.isClosed) {
      _devicesController.add(paired ? [device] : []);
    }
  }

  @override
  Stream<DeviceCompatibilityEvent> compatibilityStream() {
    if (!paired) return const Stream.empty();
    return Stream.value(
        const DeviceCompatibilityEvent(deviceUuid: uuid, compatibility: DeviceCompatibility.compatible));
  }

  @override
  Future<bool> getCameraPermissionStatus() async {
    if (cameraPermissionStatusThrows) {
      throw PlatformException(code: 'PERMISSION_ERROR', message: 'permission status unavailable');
    }
    return cameraGranted;
  }

  @override
  Future<bool> requestCameraPermission() async {
    cameraPermissionRequestCount += 1;
    if (blockCameraPermissionRequest) return Completer<bool>().future;
    cameraGranted = true;
    return true;
  }

  @override
  Future<int> startStreamSession({
    String? deviceUUID,
    int fps = 30,
    StreamQuality quality = StreamQuality.medium,
    Set<DeviceKind>? deviceKinds,
    VideoCodec videoCodec = VideoCodec.raw,
  }) async {
    streamStartCallCount += 1;
    if (failStreamStartCount > 0) {
      failStreamStartCount -= 1;
      if (leaveSessionOnFailedStart) streamSessionExists = true;
      throw const SessionError(code: DatErrorCodes.noEligibleDevice, message: 'noEligibleDevice');
    }
    if (streamSessionExists) {
      throw const SessionError(code: DatErrorCodes.sessionAlreadyExists, message: 'sessionAlreadyExists');
    }
    streamSessionExists = true;
    lastStreamDeviceUuid = deviceUUID;
    lastStreamFps = fps;
    lastStreamQuality = quality;
    return textureId;
  }

  @override
  Future<void> stopStreamSession({String? deviceUUID}) async {
    stopStreamSessionCount += 1;
    streamSessionExists = false;
  }

  @override
  Future<void> pauseStreamSession({String? deviceUUID}) async {}

  @override
  Future<void> resumeStreamSession({String? deviceUUID}) async {}

  @override
  Stream<VideoFrame> videoFramesStream() => Stream.value(
        VideoFrame(
          codec: VideoCodec.raw,
          bytes: Uint8List.fromList([0, 0, 0, 255]),
          width: 1,
          height: 1,
          ptsUs: 1,
          isKeyframe: true,
          bytesPerRow: 4,
        ),
      );

  @override
  Future<void> enableBackgroundStreaming({BackgroundNotification? androidNotification}) async {
    backgroundStreamingEnabled = true;
  }

  @override
  Future<void> disableBackgroundStreaming() async {
    backgroundStreamingEnabled = false;
  }

  @override
  Stream<StreamSessionState> streamSessionStateStream() => const Stream.empty();

  @override
  Stream<Object> streamSessionErrorStream() => const Stream.empty();

  @override
  Stream<DeviceSessionState> deviceSessionStateStream() => Stream.value(DeviceSessionState.started);

  @override
  Stream<Object> deviceSessionErrorStream() => const Stream.empty();

  @override
  Stream<VideoStreamSize> videoStreamSizeStream() => Stream.value(const VideoStreamSize(width: 640, height: 360));

  @override
  Future<FrameData?> captureStreamFrame(int textureId, {FrameFormat format = FrameFormat.rawRgba}) async {
    frameCaptureCount += 1;
    final path = capturedImagePath;
    final bytes = path == null ? fixturePngBytes : await File(path).readAsBytes();
    return FrameData(bytes: Uint8List.fromList(bytes), width: 1, height: 1, format: format);
  }

  @override
  Future<FrameData?> captureLatestFrame({double quality = 0.8}) async {
    frameCaptureCount += 1;
    final path = capturedImagePath;
    final bytes = path == null ? fixturePngBytes : await File(path).readAsBytes();
    return FrameData(bytes: Uint8List.fromList(bytes), width: 1, height: 1, format: FrameFormat.jpeg);
  }
}

final Uint8List fixturePngBytes = Uint8List.fromList(const [
  0x89,
  0x50,
  0x4e,
  0x47,
  0x0d,
  0x0a,
  0x1a,
  0x0a,
  0x00,
  0x00,
  0x00,
  0x0d,
  0x49,
  0x48,
  0x44,
  0x52,
  0x00,
  0x00,
  0x00,
  0x01,
  0x00,
  0x00,
  0x00,
  0x01,
  0x08,
  0x06,
  0x00,
  0x00,
  0x00,
  0x1f,
  0x15,
  0xc4,
  0x89,
  0x00,
  0x00,
  0x00,
  0x0a,
  0x49,
  0x44,
  0x41,
  0x54,
  0x78,
  0x9c,
  0x63,
  0x00,
  0x01,
  0x00,
  0x00,
  0x05,
  0x00,
  0x01,
  0x0d,
  0x0a,
  0x2d,
  0xb4,
  0x00,
  0x00,
  0x00,
  0x00,
  0x49,
  0x45,
  0x4e,
  0x44,
  0xae,
  0x42,
  0x60,
  0x82,
]);
