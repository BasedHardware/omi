import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/battery_widget_service.dart';

void main() {
  test('unchanged readings do not reload widget; changes and link state do', () async {
    final updates = <Map<String, Object>>[];
    final service = BatteryWidgetService.testing((info) async => updates.add(info));
    Future<void> publish(int battery, {bool connected = true}) => service.updateBatteryInfo(
          deviceName: 'Friend',
          batteryLevel: battery,
          deviceType: 'friend',
          isConnected: connected,
        );
    await publish(90);
    for (var i = 0; i < 20; i++) {
      await publish(90);
    }
    expect(updates, hasLength(1));
    await publish(89);
    await publish(89, connected: false);
    await publish(89);
    expect(updates, hasLength(4));
  });

  test('a failed widget update may retry the same reading', () async {
    var calls = 0;
    final service = BatteryWidgetService.testing((_) async {
      if (++calls == 1) throw StateError('not ready');
    });
    for (var i = 0; i < 3; i++) {
      await service.updateBatteryInfo(deviceName: 'Friend', batteryLevel: 90, deviceType: 'friend', isConnected: true);
    }
    expect(calls, 2);
  });
}
