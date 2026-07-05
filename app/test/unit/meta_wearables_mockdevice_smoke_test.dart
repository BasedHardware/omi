import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_method_channel.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
// ignore: depend_on_referenced_packages
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  late Directory tempDir;
  late _FakeMetaWearablesDatPlatform platform;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    tempDir = await Directory.systemTemp.createTemp('meta-wearables-mock-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      (call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    platform = _FakeMetaWearablesDatPlatform();
    MetaWearablesDatPlatform.instance = platform;
  });

  tearDown(() async {
    MetaWearablesDatPlatform.instance = MethodChannelMetaWearablesDat();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      null,
    );
    if (tempDir.existsSync()) {
      tempDir.deleteSync(recursive: true);
    }
  });

  test('MockDeviceKit path reaches provider queue without hardware', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: false);
    final uuid = await MetaWearablesDat.pairMockRayBanMeta();
    await MetaWearablesDat.mockPowerOn(uuid);
    await MetaWearablesDat.mockUnfold(uuid);
    await MetaWearablesDat.mockDon(uuid);
    await MetaWearablesDat.setMockPermission(MockPermission.camera, MockPermissionStatus.granted);
    await MetaWearablesDat.setMockCapturedImage(uuid, null);

    final provider = MetaWearablesProvider();
    await provider.init();
    await provider.refresh();

    expect(provider.hasDevices, isTrue);
    expect(provider.cameraPermissionGranted, isTrue);

    final textureId = await provider.startPreview();
    expect(textureId, platform.textureId);

    await provider.captureGlassesPhotoNow();

    expect(provider.pendingPhotoCount, 1);
    expect(platform.frameCaptureCount, 1);
    expect(platform.lastStreamDeviceUuid, uuid);
    expect(platform.lastStreamFps, 30);
    expect(platform.lastStreamQuality, StreamQuality.medium);

    final queueDir = Directory('${tempDir.path}/meta_glasses_photo_queue');
    expect(queueDir.existsSync(), isTrue);
    expect(queueDir.listSync().whereType<File>().length, 1);

    provider.dispose();
  });
}

class _FakeMetaWearablesDatPlatform extends MetaWearablesDatPlatform with MockPlatformInterfaceMixin {
  final int textureId = 771;
  final String uuid = 'mock-rayban-meta-1';
  final Uint8List frameBytes = Uint8List.fromList([0x89, 0x50, 0x4e, 0x47]);

  bool enabled = false;
  bool paired = false;
  bool powered = false;
  bool unfolded = false;
  bool donned = false;
  bool cameraGranted = false;
  int frameCaptureCount = 0;
  String? lastStreamDeviceUuid;
  int? lastStreamFps;
  StreamQuality? lastStreamQuality;

  DeviceInfo get device => DeviceInfo(
        uuid: uuid,
        name: 'Mock Ray-Ban Meta',
        kind: DeviceKind.rayBanMeta,
        linkState: DeviceLinkState.connected,
      );

  @override
  Future<Map<String, Object?>> dumpDiagnostics() async {
    return {'mock': true, 'paired': paired, 'cameraGranted': cameraGranted};
  }

  @override
  Future<void> enableMockDevice({bool initiallyRegistered = true, bool initialPermissionsGranted = true}) async {
    enabled = true;
    cameraGranted = initialPermissionsGranted;
  }

  @override
  Future<String> pairMockRayBanMeta() async {
    paired = true;
    return uuid;
  }

  @override
  Future<void> mockPowerOn(String uuid) async {
    powered = true;
  }

  @override
  Future<void> mockUnfold(String uuid) async {
    unfolded = true;
  }

  @override
  Future<void> mockDon(String uuid) async {
    donned = true;
  }

  @override
  Future<void> setMockPermission(String permission, String status) async {
    if (permission == MockPermission.camera.value) {
      cameraGranted = status == MockPermissionStatus.granted.value;
    }
  }

  @override
  Future<void> setMockCapturedImage(String uuid, String? filePath) async {}

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
  Stream<List<DeviceInfo>> devicesStream() {
    return Stream.value(paired ? [device] : []);
  }

  @override
  Stream<DeviceInfo?> activeDeviceStream() {
    return Stream.value(paired ? device : null);
  }

  @override
  Stream<DeviceCompatibilityEvent> compatibilityStream() {
    if (!paired) return const Stream.empty();
    return Stream.value(
      DeviceCompatibilityEvent(deviceUuid: uuid, compatibility: DeviceCompatibility.compatible),
    );
  }

  @override
  Future<bool> getCameraPermissionStatus() async => cameraGranted;

  @override
  Future<bool> requestCameraPermission() async {
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
    if (!enabled || !paired || !powered || !unfolded || !donned || !cameraGranted) {
      throw StateError('Mock device is not ready for streaming');
    }
    lastStreamDeviceUuid = deviceUUID;
    lastStreamFps = fps;
    lastStreamQuality = quality;
    return textureId;
  }

  @override
  Future<FrameData?> captureStreamFrame(int textureId, {FrameFormat format = FrameFormat.rawRgba}) async {
    frameCaptureCount += 1;
    return FrameData(bytes: frameBytes, width: 1, height: 1, format: format);
  }

  @override
  Future<FrameData?> captureLatestFrame({double quality = 0.8}) async {
    frameCaptureCount += 1;
    return FrameData(bytes: frameBytes, width: 1, height: 1, format: FrameFormat.jpeg);
  }

  @override
  Future<void> stopStreamSession({String? deviceUUID}) async {}

  @override
  Stream<StreamSessionState> streamSessionStateStream() {
    return Stream.value(StreamSessionState.streaming);
  }

  @override
  Stream<Object> streamSessionErrorStream() => const Stream.empty();

  @override
  Stream<DeviceSessionState> deviceSessionStateStream() {
    return Stream.value(DeviceSessionState.started);
  }

  @override
  Stream<Object> deviceSessionErrorStream() => const Stream.empty();

  @override
  Stream<VideoStreamSize> videoStreamSizeStream() {
    return Stream.value(const VideoStreamSize(width: 360, height: 640));
  }
}
