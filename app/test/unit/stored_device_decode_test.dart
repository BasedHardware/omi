import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> seed(Object value) async {
    SharedPreferences.setMockInitialValues({'btDevice': value});
    await SharedPreferencesUtil.init();
  }

  test('a corrupt stored device reads as empty instead of throwing', () async {
    await seed('not-json');

    expect(SharedPreferencesUtil().btDevice.id, isEmpty);
  });

  test('a stored device that decodes to a non-map reads as empty', () async {
    await seed('[1,2,3]');

    expect(SharedPreferencesUtil().btDevice.id, isEmpty);
  });

  test('btDevices still lists saved devices when the legacy entry is corrupt', () async {
    await seed('not-json');
    await SharedPreferencesUtil().btDeviceAdd(
      BtDevice(id: 'AA:BB:CC:DD:EE:FF', name: 'Omi', type: DeviceType.omi, rssi: 0),
    );
    SharedPreferences.setMockInitialValues({
      'btDevice': 'not-json',
      'btDevices': SharedPreferencesUtil().getStringList('btDevices'),
    });
    await SharedPreferencesUtil.init();

    final devices = SharedPreferencesUtil().btDevices;

    expect(devices.map((d) => d.id), contains('AA:BB:CC:DD:EE:FF'));
  });

  test('a well formed stored device still round trips', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().btDeviceSet(
      BtDevice(id: '11:22:33:44:55:66', name: 'Omi DevKit 2', type: DeviceType.omi, rssi: 0),
    );

    expect(SharedPreferencesUtil().btDevice.id, '11:22:33:44:55:66');
    expect(SharedPreferencesUtil().btDevice.name, 'Omi DevKit 2');
  });

  group('forgetting a device', () {
    BtDevice pendant(String id) => BtDevice(id: id, name: 'Omi', type: DeviceType.omi, rssi: 0);

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('removes the active device from the saved list too and leaves nothing to quarantine', () async {
      await SharedPreferencesUtil().btDeviceSet(pendant('AA:AA:AA:AA:AA:01'));
      var changes = 0;
      final subscription = SharedPreferencesUtil().deviceChanges.listen((_) => changes++);
      addTearDown(subscription.cancel);

      await SharedPreferencesUtil().btDeviceForget('AA:AA:AA:AA:AA:01');
      // Reading the cleared entry must not archive it as corrupt.
      expect(SharedPreferencesUtil().btDevice.id, isEmpty);
      await Future<void>.delayed(Duration.zero);

      expect(SharedPreferencesUtil().btDevices, isEmpty);
      expect(changes, 1, reason: 'saved reconnect retires its target on this signal');
      final keys = (await SharedPreferences.getInstance()).getKeys();
      expect(keys.where((key) => key.startsWith('btDevice.')), isEmpty);
    });

    test('keeps the other saved devices', () async {
      await SharedPreferencesUtil().btDeviceSet(pendant('AA:AA:AA:AA:AA:01'));
      await SharedPreferencesUtil().btDeviceSet(pendant('AA:AA:AA:AA:AA:02'));

      await SharedPreferencesUtil().btDeviceForget('aa:aa:aa:aa:aa:02');

      expect(SharedPreferencesUtil().btDevice.id, isEmpty);
      expect(SharedPreferencesUtil().btDevices.map((d) => d.id), ['AA:AA:AA:AA:AA:01']);
    });

    test('forgetting a saved device that is not active keeps the active one', () async {
      await SharedPreferencesUtil().btDeviceSet(pendant('AA:AA:AA:AA:AA:01'));
      await SharedPreferencesUtil().btDeviceSet(pendant('AA:AA:AA:AA:AA:02'));

      await SharedPreferencesUtil().btDeviceForget('AA:AA:AA:AA:AA:01');

      expect(SharedPreferencesUtil().btDevice.id, 'AA:AA:AA:AA:AA:02');
      expect(SharedPreferencesUtil().btDevices.map((d) => d.id), ['AA:AA:AA:AA:AA:02']);
    });

    test('forgets a device stored before the saved list existed', () async {
      SharedPreferences.setMockInitialValues({
        'btDevice': '{"id":"AA:AA:AA:AA:AA:01","name":"Omi","type":"omi","rssi":0}',
      });
      await SharedPreferencesUtil.init();
      expect(SharedPreferencesUtil().btDevices.single.id, 'AA:AA:AA:AA:AA:01');

      await SharedPreferencesUtil().btDeviceForget('AA:AA:AA:AA:AA:01');

      expect(SharedPreferencesUtil().btDevice.id, isEmpty);
      expect(SharedPreferencesUtil().btDevices, isEmpty);
    });
  });
}
