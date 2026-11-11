import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/bridges/ble_bridge.dart';

void main() {
  test('notifies the pairing-lost callback only for the stable native token', () {
    final bridge = BleBridge.instance;
    var notifications = 0;
    bridge.pairingLostCallback = () => notifications++;
    addTearDown(() => bridge.pairingLostCallback = null);

    bridge.onPeripheralDisconnected('device', 'gatt_status_133');
    bridge.onPeripheralDisconnected('device', 'pairing_lost');

    expect(notifications, 1);
  });
}
