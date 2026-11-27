import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/battery_stuck_store.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('round-trips a saved device and drops a forgotten one', () async {
    final omi = BtDevice(id: 'AA:BB', name: 'Omi', type: DeviceType.omi, rssi: -40);
    await SharedPreferencesUtil().btDeviceSet(omi);
    final at = DateTime.fromMillisecondsSinceEpoch(1764000000000);
    final store = PrefsBatteryStuckStore()..save({'AA:BB': (1, at), 'gone': (2, at)});
    expect(store.load(), {'AA:BB': (1, at)});

    await SharedPreferencesUtil().btDeviceForget('AA:BB');
    expect(store.load(), isEmpty, reason: 'Forget Device ends the stuck record');
    expect(SharedPreferencesUtil().getString(PrefsBatteryStuckStore.key), '{}',
        reason: 'the forgotten device id and reading are erased from disk');
  });

  test('a corrupt record reads as empty', () async {
    await SharedPreferencesUtil().saveString(PrefsBatteryStuckStore.key, '{"AA":"x"');
    expect(PrefsBatteryStuckStore().load(), isEmpty);
  });
}
