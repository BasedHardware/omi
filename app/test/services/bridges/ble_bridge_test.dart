import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/bridges/ble_bridge.dart';

void main() {
  test('notifies the pairing-lost callback only for the stable native token', () {
    final bridge = BleBridge.instance;
    var notifications = 0;
    bridge.pairingLostCallback = () => notifications++;
    addTearDown(() => bridge.pairingLostCallback = null);

    bridge.onPeripheralDisconnected('device', 'gatt_status_133', true);
    bridge.onPeripheralDisconnected('device', 'pairing_lost', false);

    expect(notifications, 1);
  });

  test('forwards willAutoReconnect to the connection-state callback (#6678)', () {
    final bridge = BleBridge.instance;
    bool? seenWillAutoReconnect;
    bridge.registerPeripheral(
      peripheralUuid: 'AA:BB',
      onConnectionState: (connected, error, willAutoReconnect) {
        seenWillAutoReconnect = willAutoReconnect;
      },
    );
    addTearDown(() => bridge.unregisterPeripheral('AA:BB'));

    bridge.onPeripheralDisconnected('AA:BB', 'gatt_status_133', true);
    expect(seenWillAutoReconnect, isTrue);

    bridge.onPeripheralDisconnected('AA:BB', 'unmanaged', false);
    expect(seenWillAutoReconnect, isFalse);
  });
}
