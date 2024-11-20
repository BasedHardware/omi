import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/services.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';

@GenerateMocks([DeviceService])
void main() {
  setUp(() {
    ServiceManager.init();
  });

  group('DeviceService Tests', () {
    test('Initial state', () {
      final service = DeviceService();
      expect(service.devices, isEmpty);
      // Only test the devices property for now
    });
  });
}
