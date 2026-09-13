import 'dart:io';

// Platform-interface packages are transitive test seams, not app dependencies.
// ignore: depend_on_referenced_packages
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

/// Like `setupFirebaseCoreMocks()`, plus the Crashlytics plugin constant its
/// platform interface asserts on.
class _MockFirebaseCore implements TestFirebaseCoreHostApi {
  static final _options =
      PigeonFirebaseOptions(apiKey: '123', projectId: '123', appId: '123', messagingSenderId: '123');
  static const _pluginConstants = {
    'plugins.flutter.io/firebase_crashlytics': {'isCrashlyticsCollectionEnabled': false},
  };

  @override
  Future<PigeonInitializeResponse> initializeApp(String appName, PigeonFirebaseOptions initializeAppRequest) async =>
      PigeonInitializeResponse(name: appName, options: _options, pluginConstants: _pluginConstants);

  @override
  Future<List<PigeonInitializeResponse?>> initializeCore() async => [
        PigeonInitializeResponse(name: defaultFirebaseAppName, options: _options, pluginConstants: _pluginConstants),
      ];

  @override
  Future<PigeonFirebaseOptions> optionsFromResource() async => _options;
}

BtDevice _device(String id, {DeviceType type = DeviceType.omi, String name = 'Omi'}) =>
    BtDevice(id: id, name: name, type: type, rssi: -50);

/// Role assignment when an Omi pendant and OmiGlass are connected together.
///
/// No BLE is available here (every `ensureConnection` returns null), so the
/// connect path degrades to state bookkeeping: what this file pins down is
/// which device the provider treats as the audio device, which one as the
/// photo companion, and that the capture controller is told the same thing.
void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return Directory.systemTemp.path;
        return null;
      },
    );
    // The disconnect path logs to Crashlytics; give it a mock Firebase app and
    // a silent channel so teardown is exercised without the native plugin.
    TestFirebaseCoreHostApi.setup(_MockFirebaseCore());
    await Firebase.initializeApp();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/firebase_crashlytics'),
      (MethodCall call) async => null,
    );
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialised by another test in this isolate.
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    // Batch mode keeps streamDeviceRecording off the transcription socket.
    SharedPreferencesUtil().batchModeEnabled = true;
    DeviceProvider.disconnectDebounceDelay = Duration.zero;
  });

  tearDown(() {
    SharedPreferencesUtil().batchModeEnabled = false;
    DeviceProvider.disconnectDebounceDelay = const Duration(milliseconds: 500);
    AnalyticsManager.resetForTesting();
  });

  Future<void> _awaitDisconnectHandling(DeviceProvider device) async {
    await Future<void>.delayed(Duration.zero);
    await device.pendingRolesReconciliation;
  }

  Future<(DeviceProvider, CaptureProvider)> providers() async {
    final capture = CaptureProvider();
    final device = DeviceProvider();
    device.setProviders(capture, LocalRecordingsProvider());
    addTearDown(() async {
      // The disconnect path fires setConnectedDevice(null) without awaiting it
      // (diagnostics are best-effort); let that settle before disposing.
      await Future<void>.delayed(const Duration(milliseconds: 100));
      device.dispose();
      capture.dispose();
    });
    return (device, capture);
  }

  final omi = _device('omi-1');
  final glass = _device('glass-1', type: DeviceType.openglass, name: 'OmiGlass');

  test('pendant carries audio, glasses join as the photo companion', () async {
    final (device, capture) = await providers();

    await device.registerConnectedDevice(omi);
    expect(device.connectedDevice?.id, 'omi-1');
    expect(device.isConnected, isTrue);
    expect(device.companionDevice, isNull);
    expect(capture.recordingDevice?.id, 'omi-1');
    expect(capture.companionPhotoDevice, isNull);

    await device.registerConnectedDevice(glass);
    expect(device.connectedDevice?.id, 'omi-1', reason: 'the pendant keeps the audio role');
    expect(device.companionDevice?.id, 'glass-1');
    expect(device.isCompanionConnected, isTrue);
    expect(device.connectedDevices.map((d) => d.id), ['omi-1', 'glass-1']);
    expect(capture.recordingDevice?.id, 'omi-1');
    expect(capture.companionPhotoDevice?.id, 'glass-1');
    expect(capture.photoDevice?.id, 'glass-1');
  });

  test('glasses connected first are demoted to the photo role when the pendant arrives', () async {
    final (device, capture) = await providers();

    await device.registerConnectedDevice(glass);
    expect(device.connectedDevice?.id, 'glass-1', reason: 'alone, OmiGlass records audio and photos');
    expect(device.companionDevice, isNull);
    expect(capture.recordingDevice?.id, 'glass-1');
    expect(capture.photoDevice?.id, 'glass-1');

    await device.registerConnectedDevice(omi);
    expect(device.connectedDevice?.id, 'omi-1');
    expect(device.companionDevice?.id, 'glass-1');
    expect(capture.recordingDevice?.id, 'omi-1');
    expect(capture.companionPhotoDevice?.id, 'glass-1');
  });

  test('when the pendant drops, the glasses take over audio and keep photos', () async {
    final (device, capture) = await providers();
    await device.registerConnectedDevice(omi);
    await device.registerConnectedDevice(glass);

    device.onDeviceConnectionStateChanged('omi-1', DeviceConnectionState.disconnected);
    await _awaitDisconnectHandling(device);

    expect(device.connectedDevice?.id, 'glass-1');
    expect(device.companionDevice, isNull);
    expect(device.connectedDevices.map((d) => d.id), ['glass-1']);
    expect(capture.recordingDevice?.id, 'glass-1');
    expect(capture.companionPhotoDevice, isNull);
    expect(capture.photoDevice?.id, 'glass-1');
  });

  test('when the glasses drop, the pendant keeps recording without a photo device', () async {
    final (device, capture) = await providers();
    await device.registerConnectedDevice(omi);
    await device.registerConnectedDevice(glass);

    device.onDeviceConnectionStateChanged('glass-1', DeviceConnectionState.disconnected);
    await _awaitDisconnectHandling(device);

    expect(device.connectedDevice?.id, 'omi-1');
    expect(device.isConnected, isTrue);
    expect(device.companionDevice, isNull);
    expect(capture.recordingDevice?.id, 'omi-1');
    expect(capture.companionPhotoDevice, isNull);
  });

  test('a stray disconnect for an unknown device changes nothing', () async {
    final (device, _) = await providers();
    await device.registerConnectedDevice(omi);

    device.onDeviceConnectionStateChanged('someone-elses-device', DeviceConnectionState.disconnected);
    await _awaitDisconnectHandling(device);

    expect(device.connectedDevice?.id, 'omi-1');
    expect(device.isConnected, isTrue);
  });

  test('forgetting the companion drops it from prefs and from the photo role', () async {
    final (device, capture) = await providers();
    await SharedPreferencesUtil().btDeviceSet(omi);
    SharedPreferencesUtil().companionBtDevice = glass;
    await device.registerConnectedDevice(omi);
    await device.registerConnectedDevice(glass);
    expect(device.pairedCompanionDevice?.id, 'glass-1');

    await device.forgetCompanionDevice();

    expect(SharedPreferencesUtil().companionBtDevice, isNull);
    expect(SharedPreferencesUtil().pairedDeviceIds, ['omi-1']);
    expect(device.pairedCompanionDevice, isNull);
    expect(device.companionDevice, isNull);
    expect(device.connectedDevice?.id, 'omi-1');
    expect(capture.companionPhotoDevice, isNull);
  });

  test('forgetting the primary promotes the connected companion to the audio role', () async {
    final (device, capture) = await providers();
    await SharedPreferencesUtil().btDeviceSet(omi);
    SharedPreferencesUtil().companionBtDevice = glass;
    await device.registerConnectedDevice(omi);
    await device.registerConnectedDevice(glass);

    await device.forgetDevice('omi-1');

    expect(SharedPreferencesUtil().btDevice.id, 'glass-1');
    expect(SharedPreferencesUtil().companionBtDevice, isNull);
    expect(device.connectedDevice?.id, 'glass-1');
    expect(device.companionDevice, isNull);
    expect(capture.recordingDevice?.id, 'glass-1');
  });

  test('pairedCompanionDevice reports the saved device that is not the current primary', () async {
    final (device, _) = await providers();
    await SharedPreferencesUtil().btDeviceSet(omi);
    SharedPreferencesUtil().companionBtDevice = glass;

    // Nothing connected: primary slot is the paired device, companion slot is the second one.
    await device.getDeviceInfo();
    expect(device.pairedDevice?.id, 'omi-1');
    expect(device.pairedCompanionDevice?.id, 'glass-1');

    // Only the glasses online: they are the connected device, the pendant is the offline second one.
    await device.registerConnectedDevice(glass);
    expect(device.connectedDevice?.id, 'glass-1');
    expect(device.pairedCompanionDevice?.id, 'omi-1');
    expect(SharedPreferencesUtil().btDevice.id, 'omi-1', reason: 'roles never rewrite the saved slots');
    expect(SharedPreferencesUtil().companionBtDevice?.id, 'glass-1');
  });
}
