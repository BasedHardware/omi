import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

BtDevice _device({String id = 'AA:BB:CC:DD:EE:FF', String name = 'Omi'}) =>
    BtDevice(id: id, name: name, type: DeviceType.omi, rssi: 0);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('device custom name', () {
    test('falls back to the advertised name when nothing is stored', () {
      expect(SharedPreferencesUtil().getDeviceCustomName('AA:BB:CC:DD:EE:FF'), isNull);
      expect(_device().displayName, 'Omi');
    });

    test('returns the stored name once set', () async {
      await SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:FF', 'Studio Pendant');

      expect(_device().displayName, 'Studio Pendant');
    });

    test('survives a reconnect that rewrites the paired device and advertised name', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.setDeviceCustomName('AA:BB:CC:DD:EE:FF', 'Studio Pendant');

      await prefs.btDeviceSet(_device());
      prefs.deviceName = 'Omi';

      expect(prefs.btDevice.name, 'Omi');
      expect(prefs.btDevice.displayName, 'Studio Pendant');
    });

    test('keeps names separate per device id', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.setDeviceCustomName('AA:BB:CC:DD:EE:FF', 'Studio Pendant');
      await prefs.setDeviceCustomName('11:22:33:44:55:66', 'Travel Pendant');

      expect(_device().displayName, 'Studio Pendant');
      expect(_device(id: '11:22:33:44:55:66', name: 'Omi DevKit 2').displayName, 'Travel Pendant');
    });

    test('a blank name clears the override instead of storing it', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.setDeviceCustomName('AA:BB:CC:DD:EE:FF', 'Studio Pendant');

      await prefs.setDeviceCustomName('AA:BB:CC:DD:EE:FF', '   ');

      expect(prefs.deviceCustomNames.containsKey('AA:BB:CC:DD:EE:FF'), isFalse);
      expect(_device().displayName, 'Omi');
    });

    test('trims surrounding whitespace before storing', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.setDeviceCustomName('AA:BB:CC:DD:EE:FF', '  Studio Pendant  ');

      expect(prefs.deviceCustomNames['AA:BB:CC:DD:EE:FF'], 'Studio Pendant');
    });

    test('ignores an empty device id', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.setDeviceCustomName('', 'Nowhere');

      expect(prefs.deviceCustomNames, isEmpty);
      expect(prefs.getDeviceCustomName(''), isNull);
    });

    test('unpairing clears only that device override', () async {
      final prefs = SharedPreferencesUtil();
      await prefs.setDeviceCustomName('AA:BB:CC:DD:EE:FF', 'Studio Pendant');
      await prefs.setDeviceCustomName('11:22:33:44:55:66', 'Travel Pendant');

      await prefs.clearDeviceCustomName('AA:BB:CC:DD:EE:FF');

      expect(_device().displayName, 'Omi');
      expect(prefs.deviceCustomNames['11:22:33:44:55:66'], 'Travel Pendant');
    });

    test('falls back to the advertised name when stored json is corrupt', () async {
      SharedPreferences.setMockInitialValues({'deviceCustomNames': 'not-json'});
      await SharedPreferencesUtil.init();

      expect(SharedPreferencesUtil().deviceCustomNames, isEmpty);
      expect(_device().displayName, 'Omi');
    });
  });
}
