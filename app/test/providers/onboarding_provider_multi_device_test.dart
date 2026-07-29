import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/onboarding_provider.dart';

BtDevice _device({required String id, required String name, DeviceType type = DeviceType.omi, int rssi = -60}) =>
    BtDevice(id: id, name: name, type: type, rssi: rssi);

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('multi-device saved devices', () {
    test('btDeviceSet appends unique saved devices without dropping the active device', () async {
      final first = _device(id: 'AA:AA:AA:AA:AA:01', name: 'Omi One');
      final second = _device(id: 'AA:AA:AA:AA:AA:02', name: 'Omi Two', rssi: -40);

      await SharedPreferencesUtil().btDeviceSet(first);
      await SharedPreferencesUtil().btDeviceSet(second);
      await SharedPreferencesUtil().btDeviceSet(second.copyWith(name: 'Omi Two Nearby', rssi: -35));

      expect(SharedPreferencesUtil().btDevice.id, second.id);
      expect(SharedPreferencesUtil().btDevices.map((device) => device.id), [first.id, second.id]);
      expect(SharedPreferencesUtil().btDevices.last.name, 'Omi Two Nearby');
    });

    test('visibleDeviceList keeps offline saved devices and replaces them with live scan data', () async {
      final savedOffline = _device(id: 'AA:AA:AA:AA:AA:01', name: 'Saved Offline');
      final savedOnline = _device(id: 'AA:AA:AA:AA:AA:02', name: 'Saved Old', rssi: -80);
      final liveOnline = savedOnline.copyWith(name: 'Saved Online', rssi: -30);
      final liveNew = _device(id: 'AA:AA:AA:AA:AA:03', name: 'New Nearby', rssi: -45);

      await SharedPreferencesUtil().btDeviceSet(savedOffline);
      await SharedPreferencesUtil().btDeviceSet(savedOnline);

      final provider = OnboardingProvider();
      provider.onDevices([liveOnline, liveNew]);

      expect(provider.savedDeviceList.map((device) => device.id), [savedOffline.id, savedOnline.id]);
      expect(provider.visibleDeviceList.map((device) => device.id), [savedOffline.id, savedOnline.id, liveNew.id]);
      expect(provider.visibleDeviceList[1].name, 'Saved Online');
      expect(provider.visibleDeviceList[1].rssi, -30);
    });

    test('nearby count and online state ignore saved devices that are not advertising', () async {
      final savedOffline = _device(id: 'AA:AA:AA:AA:AA:01', name: 'Saved Offline');
      final liveNew = _device(id: 'AA:AA:AA:AA:AA:02', name: 'New Nearby', rssi: -45);

      await SharedPreferencesUtil().btDeviceSet(savedOffline);

      final provider = OnboardingProvider();
      provider.onDevices([liveNew]);

      expect(provider.visibleDeviceList.map((device) => device.id), [savedOffline.id, liveNew.id]);
      expect(provider.nearbyDeviceCount, 1);
      expect(provider.isDeviceOnline(savedOffline), isFalse);
      expect(provider.isDeviceOnline(liveNew), isTrue);
    });
  });
}
