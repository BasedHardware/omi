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
}
