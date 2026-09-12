import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/onboarding_provider.dart';

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('device custom names (local rename)', () {
    test('returns empty string when no custom name was saved', () {
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), '');
      expect(SharedPreferencesUtil().deviceCustomNames, isEmpty);
    });

    test('setDeviceCustomName stores and returns the trimmed name by device id', () {
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', '  My Omi  ');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), 'My Omi');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:02'), '');
    });

    test('names are persisted per device id and survive re-init', () async {
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', 'Desk Omi');
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:02', 'Gym Omi');

      // Re-init from the same mock backing store simulates an app restart.
      await SharedPreferencesUtil.init();
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), 'Desk Omi');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:02'), 'Gym Omi');
    });

    test('saving fewer than 2 characters clears the custom name', () {
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', 'Desk Omi');
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', ' X ');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), '');

      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', 'Desk Omi');
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', '');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), '');
    });

    test('clearDeviceCustomName removes only the targeted device entry', () {
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:01', 'Desk Omi');
      SharedPreferencesUtil().setDeviceCustomName('AA:BB:CC:DD:EE:02', 'Gym Omi');

      SharedPreferencesUtil().clearDeviceCustomName('AA:BB:CC:DD:EE:01');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), '');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:02'), 'Gym Omi');
    });

    test('corrupt stored JSON falls back to an empty map instead of crashing', () async {
      await SharedPreferencesUtil().saveString('deviceCustomNames', '{not-json');
      expect(SharedPreferencesUtil().deviceCustomNames, isEmpty);
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), '');
    });

    test('non-string persisted values are discarded instead of rendered', () async {
      await SharedPreferencesUtil().saveString('deviceCustomNames',
          '{"AA:BB:CC:DD:EE:01":"Desk Omi","AA:BB:CC:DD:EE:02":false,"AA:BB:CC:DD:EE:03":null,"AA:BB:CC:DD:EE:04":{"nested":true}}');
      final names = SharedPreferencesUtil().deviceCustomNames;
      expect(names, {'AA:BB:CC:DD:EE:01': 'Desk Omi'});
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:01'), 'Desk Omi');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:02'), '');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:03'), '');
      expect(SharedPreferencesUtil().deviceCustomName('AA:BB:CC:DD:EE:04'), '');
    });

    test('displayNameFor prefers the custom name and falls back to the BLE name', () {
      final provider = OnboardingProvider();
      final device = BtDevice(id: 'AA:BB:CC:DD:EE:01', name: 'Omi', type: DeviceType.omi, rssi: -50);
      expect(provider.displayNameFor(device), 'Omi');

      SharedPreferencesUtil().setDeviceCustomName(device.id, 'Desk Omi');
      expect(provider.displayNameFor(device), 'Desk Omi');

      SharedPreferencesUtil().clearDeviceCustomName(device.id);
      expect(provider.displayNameFor(device), 'Omi');
    });
  });
}
