import 'dart:io';

// Platform-interface packages are transitive test seams, not app dependencies.
// ignore: depend_on_referenced_packages
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/services.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

BtDevice _device(String id, {DeviceType type = DeviceType.omi, String name = 'Omi'}) =>
    BtDevice(id: id, name: name, type: type, rssi: -50);

/// Which device the capture pipeline streams photos from when an OmiGlass is
/// paired next to the recording device. No BLE here: `ensureConnection`
/// returns null, so these pin the role bookkeeping the streaming code reads.
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
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialised by another test in this isolate.
    }
  });

  final omi = _device('omi-1');
  final glass = _device('glass-1', type: DeviceType.openglass, name: 'OmiGlass');

  test('photos follow the companion glasses while the pendant records audio', () async {
    final provider = CaptureProvider();
    addTearDown(provider.dispose);
    provider.updateRecordingDevice(omi);
    expect(provider.photoDevice?.id, 'omi-1',
        reason: 'without a companion, the recording device is the camera candidate');

    await provider.updatePhotoDevice(glass);

    expect(provider.recordingDevice?.id, 'omi-1');
    expect(provider.companionPhotoDevice?.id, 'glass-1');
    expect(provider.photoDevice?.id, 'glass-1');
    expect(provider.photoStreamDeviceIdForTesting, isNull, reason: 'no session is active, nothing streams yet');
  });

  test('the recording device is never its own companion', () async {
    final provider = CaptureProvider();
    addTearDown(provider.dispose);
    provider.updateRecordingDevice(glass);

    await provider.updatePhotoDevice(glass);

    expect(provider.companionPhotoDevice, isNull);
    expect(provider.photoDevice?.id, 'glass-1');
  });

  test('promoting the companion to the recording device clears the companion role', () async {
    final provider = CaptureProvider();
    addTearDown(provider.dispose);
    provider.updateRecordingDevice(omi);
    await provider.updatePhotoDevice(glass);

    provider.updateRecordingDevice(glass);

    expect(provider.recordingDevice?.id, 'glass-1');
    expect(provider.companionPhotoDevice, isNull);
    expect(provider.photoDevice?.id, 'glass-1');
  });

  test('clearing the companion falls back to the recording device', () async {
    final provider = CaptureProvider();
    addTearDown(provider.dispose);
    provider.updateRecordingDevice(omi);
    await provider.updatePhotoDevice(glass);
    var notifications = 0;
    provider.addListener(() => notifications++);

    await provider.updatePhotoDevice(null);
    expect(provider.companionPhotoDevice, isNull);
    expect(provider.photoDevice?.id, 'omi-1');
    expect(notifications, 1);

    await provider.updatePhotoDevice(null);
    expect(notifications, 1, reason: 'an unchanged companion must not churn listeners');
  });
}
