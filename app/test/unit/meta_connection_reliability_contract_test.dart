import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:shared_preferences/shared_preferences.dart';

String _read(String path) => File(path).readAsStringSync();

String _functionBody(String source, String functionName) {
  final start = source.indexOf(functionName);
  expect(start, isNonNegative, reason: '$functionName missing');
  final asyncStart = source.indexOf('async', start);
  expect(asyncStart, isNonNegative, reason: '$functionName must be async');
  final open = source.indexOf('{', asyncStart);
  var depth = 0;
  for (var i = open; i < source.length; i++) {
    final char = source[i];
    if (char == '{') depth++;
    if (char == '}') depth--;
    if (depth == 0) return source.substring(open + 1, i);
  }
  fail('Could not parse $functionName body');
}

void main() {
  group('Meta connection reliability contracts', () {
    test('DeviceConnection refuses a transport when ping cannot prove liveness', () {
      final source = _read('lib/services/devices/device_connection.dart');
      final connect = _functionBody(source, 'Future<void> connect');

      expect(connect, contains('final connected = await ping();'));
      expect(connect, contains('if (!connected)'));
      expect(connect, contains('Transport ping failed'));
    });

    test('Meta snapshot does not fake an active device from the device list', () {
      final source = _read('lib/services/devices/meta_wearables_service.dart');
      final activeSnapshot = _functionBody(source, 'Future<DeviceInfo?> _activeDeviceSnapshot');

      expect(activeSnapshot, isNot(contains('devices.isNotEmpty ? devices.first : null')));
      expect(activeSnapshot, contains('return null;'));
    });

    test('connection page exposes saved devices first and auto-connects them when seen online', () {
      final prefs = _read('lib/backend/preferences.dart');
      final provider = _read('lib/providers/onboarding_provider.dart');
      final page = _read('lib/pages/onboarding/find_device/found_devices.dart');

      expect(prefs, contains('List<BtDevice> get btDevices'));
      expect(prefs, contains('Future<void> btDeviceAdd'));
      expect(prefs, contains('Future<void> btDeviceRemove'));

      expect(provider, contains('savedDeviceList'));
      expect(provider, contains('visibleDeviceList'));
      expect(provider, contains('_autoConnectSavedDeviceIfVisible'));
      expect(provider, contains('isSavedDevice'));
      expect(provider, contains('if (!isSavedDevice(device))'));

      expect(page, contains('provider.visibleDeviceList'));
      expect(page, contains('provider.isSavedDevice(device)'));
      expect(page, contains('context.l10n.saved'));
    });
  });

  group('saved device preferences', () {
    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('stores multiple saved devices and replaces by id', () async {
      final prefs = SharedPreferencesUtil();
      final metaA = BtDevice(id: 'meta-a', name: 'Meta A', type: DeviceType.metaWearables, rssi: -40);
      final metaAUpdated = BtDevice(id: 'meta-a', name: 'Meta A Updated', type: DeviceType.metaWearables, rssi: -35);
      final omi = BtDevice(id: 'omi-a', name: 'Omi A', type: DeviceType.omi, rssi: -50);

      await prefs.btDeviceAdd(metaA);
      await prefs.btDeviceAdd(omi);
      await prefs.btDeviceAdd(metaAUpdated);

      expect(prefs.btDevices.map((device) => device.id), ['meta-a', 'omi-a']);
      expect(prefs.btDevices.first.name, 'Meta A Updated');
    });
  });
}
