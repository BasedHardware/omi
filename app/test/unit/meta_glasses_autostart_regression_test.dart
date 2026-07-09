import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_method_channel.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/services/devices/meta_wearables_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/meta_wearables_mock_harness.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  late Directory tempDir;
  late MetaWearablesMockHarness harness;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'metaGlassesAutoCapture': true});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('meta-glasses-autostart-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      (call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    harness = MetaWearablesMockHarness();
    MetaWearablesDatPlatform.instance = harness.platform;
  });

  tearDown(() {
    MetaWearablesDatPlatform.instance = MethodChannelMetaWearablesDat();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('registered visible glasses do not auto-start without explicit opt-in', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();

    provider.attachCaptureController(controller);
    await _drainAutoStart();

    expect(provider.autoCaptureEnabled, isFalse);
    expect(provider.isCapturing, isFalse);
    expect(harness.platform.frameCaptureCount, 0);
    expect(controller.ingestedImages, isEmpty);

    provider.dispose();
  });

  test('registered visible glasses auto-start with DAT auto selector when link state is stale', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();

    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(provider.devices.single.linkState, DeviceLinkState.disconnected);
    expect(provider.isCapturing, isTrue);
    expect(controller.streamRecordingCount, 0);
    expect(harness.platform.lastStreamDeviceUuid, isNull);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('auto-start keeps capture alive when a stale glasses link later becomes eligible', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();
    provider.attachCaptureController(controller);
    await _drainAutoStart();

    await _waitFor(() => provider.isCapturing);
    expect(provider.isCapturing, isTrue);
    expect(controller.streamRecordingCount, 0);
    expect(harness.platform.lastStreamDeviceUuid, isNull);

    await _makeMockEligible();
    await _drainAutoStart();

    expect(provider.devices.single.linkState, DeviceLinkState.connected);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('auto-start does not depend on link-state stream events when paired glasses are visible', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    harness.platform.emitDeviceChanges = false;

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();
    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(provider.isCapturing, isTrue);
    expect(controller.streamRecordingCount, 0);
    expect(harness.platform.lastStreamDeviceUuid, isNull);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('auto-start targets the DAT active eligible device instead of auto selector', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    await _makeMockEligible();

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();

    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(controller.streamRecordingCount, 0);
    expect(provider.devices.single.linkState, DeviceLinkState.connected);
    expect(provider.isActive(provider.devices.single), isTrue);
    expect(harness.platform.lastStreamDeviceUuid, RecordingMetaWearablesMockPlatform.uuid);

    provider.dispose();
  });

  test('auto-started camera stream never starts phone mic recording', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    await _makeMockEligible();

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = _BlockingCaptureController();

    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(controller.streamRecordingCount, 0);
    expect(harness.platform.backgroundStreamingEnabled, isTrue);
    expect(harness.platform.lastStreamDeviceUuid, RecordingMetaWearablesMockPlatform.uuid);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('registered visible glasses use granted camera permission even when active device is temporarily none',
      () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    await _makeMockEligible();
    harness.platform.reportsActiveDevice = false;

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();

    expect(provider.devices, isNotEmpty);
    expect(provider.cameraPermissionGranted, isTrue);

    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(controller.streamRecordingCount, 0);
    expect(harness.platform.lastStreamDeviceUuid, RecordingMetaWearablesMockPlatform.uuid);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('auto-start waits for initial permission snapshot instead of hanging in permission request', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    await _makeMockEligible();
    harness.platform.reportsActiveDevice = false;
    harness.platform.blockCameraPermissionRequest = true;

    final provider = MetaWearablesProvider();
    final controller = RecordingCaptureController();
    provider.attachCaptureController(controller);
    await provider.init();
    await _drainAutoStart();

    expect(harness.platform.cameraPermissionRequestCount, 0);
    expect(harness.platform.lastStreamDeviceUuid, RecordingMetaWearablesMockPlatform.uuid);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('auto-start streams directly when permission status is unavailable but glasses are visible', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    await _makeMockEligible();
    harness.platform.reportsActiveDevice = false;
    harness.platform.cameraPermissionStatusThrows = true;
    harness.platform.blockCameraPermissionRequest = true;

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();
    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(provider.devices, isNotEmpty);
    expect(provider.cameraPermissionState, MetaGlassesCameraPermissionState.unavailable);
    expect(harness.platform.cameraPermissionRequestCount, 0);
    expect(harness.platform.lastStreamDeviceUuid, RecordingMetaWearablesMockPlatform.uuid);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('stream start failure during initial capture schedules the bounded camera retry', () async {
    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: true);
    await MetaWearablesDat.pairMockRayBanMeta();
    await _enableAutoCaptureForTest();
    await _makeMockEligible();
    harness.platform.failStreamStartCount = 1;
    harness.platform.leaveSessionOnFailedStart = true;

    final provider = MetaWearablesProvider();
    await provider.init();
    final controller = RecordingCaptureController();
    provider.attachCaptureController(controller);
    await _drainAutoStart();
    await _waitFor(() => provider.isCapturing);

    expect(harness.platform.streamStartCallCount, 1);
    expect(harness.platform.frameCaptureCount, 0);

    await Future<void>.delayed(const Duration(seconds: 9));
    await _drainAutoStart();

    expect(harness.platform.streamStartCallCount, 2);
    expect(harness.platform.stopStreamSessionCount, 1);
    expect(harness.platform.frameCaptureCount, 1);
    expect(controller.ingestedImages, hasLength(1));

    provider.dispose();
  });

  test('old gesture prefs do not re-enable unsupported gestures', () async {
    SharedPreferences.setMockInitialValues({
      'metaGlassesGesturesEnabled': false,
    });
    await SharedPreferencesUtil.init();

    final provider = MetaWearablesProvider();
    await provider.init();

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool('metaGlassesGesturesEnabled'), isFalse);
    expect(prefs.getBool('metaGlassesGesturesRuntimeFixMigrated'), isNull);

    provider.dispose();
  });

  test('legacy gesture migration marker is ignored', () async {
    SharedPreferences.setMockInitialValues({
      'metaGlassesGesturesEnabled': false,
      'metaGlassesGesturesRuntimeFixMigrated': true,
    });
    await SharedPreferencesUtil.init();

    final provider = MetaWearablesProvider();
    await provider.init();

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool('metaGlassesGesturesEnabled'), isFalse);
    expect(prefs.getBool('metaGlassesGesturesRuntimeFixMigrated'), isTrue);

    provider.dispose();
  });
}

Future<void> _drainAutoStart() async {
  for (var i = 0; i < 5; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

Future<void> _enableAutoCaptureForTest() async {
  await SharedPreferencesUtil().saveBool('metaGlassesAutoCapture', true);
}

Future<void> _makeMockEligible() async {
  await MetaWearablesDat.mockPowerOn(RecordingMetaWearablesMockPlatform.uuid);
  await MetaWearablesDat.mockUnfold(RecordingMetaWearablesMockPlatform.uuid);
  await MetaWearablesDat.mockDon(RecordingMetaWearablesMockPlatform.uuid);
}

Future<void> _waitFor(bool Function() condition) async {
  for (var i = 0; i < 20; i++) {
    if (condition()) return;
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('Timed out waiting for async auto-start to settle.');
}

class _BlockingCaptureController extends RecordingCaptureController {
  final Completer<void> _neverReturns = Completer<void>();

  @override
  Future<void> streamRecording() async {
    streamRecordingCount += 1;
    return _neverReturns.future;
  }
}
