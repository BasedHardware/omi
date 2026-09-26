import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices.dart';

void main() {
  test('ensureConnection is blocked while stale bond recovery is required', () async {
    final service = DeviceService(connectionBuilder: (_) => null);
    service.requireStaleBondRecovery();

    final result = await service.ensureConnection('AA:BB:CC:DD:EE:FF', force: true);

    expect(result, isNull);
  });

  test('forgetDevice clears stale bond recovery requirement', () async {
    final service = DeviceService(connectionBuilder: (_) => null);
    service.requireStaleBondRecovery();

    await service.forgetDevice('AA:BB:CC:DD:EE:FF');

    expect(service.staleBondRecoveryRequired, isFalse);
  });
}
