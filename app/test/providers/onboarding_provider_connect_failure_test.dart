import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/services.dart';

BtDevice _device({required String id, required String name, DeviceType type = DeviceType.omi, int rssi = -60}) =>
    BtDevice(id: id, name: name, type: type, rssi: rssi);

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized
    }
  });

  group('OnboardingProvider connection failure handling', () {
    test('handleTap failure retains found device row and emits error notification', () async {
      final provider = OnboardingProvider();
      final deviceProvider = DeviceProvider();
      provider.deviceProvider = deviceProvider;

      final testDevice = _device(id: 'FF:EE:DD:CC:BB:AA', name: 'My Omi Device');
      provider.onDevices([testDevice]);

      expect(provider.visibleDeviceList.any((d) => d.id == testDevice.id), isTrue);
      expect(provider.isSavedDevice(testDevice), isFalse);

      String? receivedError;
      provider.errorListener = (error) {
        receivedError = error;
      };

      // Calling handleTap with an unconnectable fake device will trigger the catch block.
      await provider.handleTap(
        device: testDevice,
        isFromOnboarding: false,
      );

      // Verify state was reset properly so user can tap again
      expect(provider.isClicked, isFalse);
      expect(provider.connectingToDeviceId, isNull);
      expect(provider.isConnected, isFalse);

      // Key regression fix: the device must NOT have been silently removed from the list!
      expect(provider.visibleDeviceList.any((d) => d.id == testDevice.id), isTrue);
      expect(provider.foundDevicesMap.containsKey(testDevice.id), isTrue);

      // Error notification must have fired for FoundDevices to display feedback
      expect(receivedError, 'DEVICE_CONNECT_FAILED');
    });
  });
}
