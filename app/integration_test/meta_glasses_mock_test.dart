import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_method_channel.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/providers/meta_wearables_provider.dart';

import '../test/support/meta_wearables_mock_harness.dart';

const bool _mockEnabled = kDebugMode && bool.fromEnvironment('OMI_META_MOCK');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const pathProviderChannel = MethodChannel('plugins.flutter.io/path_provider');
  late Directory tempDir;
  late MetaWearablesMockHarness harness;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    tempDir = await Directory.systemTemp.createTemp('meta-glasses-mock-it-');
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

  tearDown(() async {
    MetaWearablesDatPlatform.instance = MethodChannelMetaWearablesDat();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      pathProviderChannel,
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('Mock Device Kit Ray-Ban photo capture flows through queue into conversation', () async {
    if (!_mockEnabled) {
      markTestSkipped('Run with --dart-define=OMI_META_MOCK=true in debug test mode.');
      return;
    }

    final fixture = await harness.writeFixtureImage(tempDir);

    await MetaWearablesDat.enableMockDevice(initiallyRegistered: true, initialPermissionsGranted: false);
    final uuid = await MetaWearablesDat.pairMockRayBanMeta();
    await MetaWearablesDat.mockPowerOn(uuid);
    await MetaWearablesDat.mockUnfold(uuid);
    await MetaWearablesDat.mockDon(uuid);
    await MetaWearablesDat.setMockPermission(MockPermission.camera, MockPermissionStatus.granted);
    await MetaWearablesDat.setMockCapturedImage(uuid, fixture.path);

    final provider = MetaWearablesProvider();
    final capture = RecordingCaptureController();
    await provider.init();
    await provider.refresh();

    expect(provider.hasDevices, isTrue);
    expect(provider.hasLinkedDevices, isTrue);
    expect(provider.cameraPermissionGranted, isTrue);

    final started = await provider.startCapture(capture);
    expect(started, isTrue);

    expect(harness.platform.frameCaptureCount, 1);
    expect(capture.ingestedImages, hasLength(1));
    expect(capture.addToUiValues.single, isTrue);
    expect(provider.pendingPhotoCount, 0);
    final queueDir = Directory('${tempDir.path}/meta_glasses_photo_queue');
    expect(queueDir.existsSync() ? queueDir.listSync().whereType<File>() : const <File>[], isEmpty);

    await provider.stopCapture();
    provider.dispose();
    capture.dispose();
  });

  test('mock devices cover linked and unlinked sanitizer states', () async {
    final result = MetaWearablesProvider.sanitizeDevices(harness.devicesInTwoLinkStates());

    expect(result, hasLength(2));
    expect(result.where((device) => device.linkState == DeviceLinkState.connected), hasLength(1));
    expect(result.where((device) => device.linkState == DeviceLinkState.disconnected), hasLength(1));
  });
}
