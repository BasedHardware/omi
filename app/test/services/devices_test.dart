import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import '../test_utils.dart';
import '../mocks/mocks.mocks.dart';

void main() {
  late DeviceService deviceService;
  late MockWatchManager watchManager;
  late MockIDeviceServiceSubsciption subscription;

  setUp(() {
    watchManager = MockWatchManager();
    deviceService = DeviceService();
    subscription = MockIDeviceServiceSubsciption();
    deviceService.subscribe(subscription, Object());
  });

  group('DeviceService Watch Tests', () {
    test('discovers watch when available', () async {
      when(watchManager.isWatchAvailable()).thenAnswer((_) async => true);

      await deviceService.discover();

      verify(subscription.onDevices(any)).called(1);
      final devices = verify(subscription.onDevices(captureAny)).captured.single as List<BtDevice>;
      expect(devices.any((d) => d.type == DeviceType.watch), true);
    });
  });
}
