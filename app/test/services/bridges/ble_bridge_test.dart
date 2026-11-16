import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/bridges/ble_bridge.dart';

void main() {
  test('recording reconnect classification is exact, device scoped and cleared on readiness', () {
    final bridge = BleBridge.instance;
    addTearDown(() => bridge.clearPeripheralForTesting('device'));
    for (final reason in [
      'connection_timeout',
      'remote_device_terminated',
      'gatt_status_8',
      'gatt_status_19',
      'gatt_status_34'
    ]) {
      bridge.onPeripheralDisconnected('device', reason);
      expect(bridge.allowsRecordingReconnect('DEVICE'), isTrue);
      expect(bridge.allowsRecordingReconnect('other'), isFalse);
      bridge.onDeviceReady('device', []);
      expect(bridge.allowsRecordingReconnect('device'), isFalse);
    }
    for (final reason in [
      'manual',
      'pairing_lost',
      'bluetooth_off',
      'gatt_status_133',
      'capture_recovery',
      'clean_disconnect',
      null
    ]) {
      bridge.onPeripheralDisconnected('device', reason);
      expect(bridge.allowsRecordingReconnect('device'), isFalse);
    }
  });

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
