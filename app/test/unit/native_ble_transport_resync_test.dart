import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

class _FakeBleHostApi extends BleHostApi {
  final List<String> subscribed = [];

  @override
  Future<void> manageDevice(String uuid, bool requiresBond) async {}

  @override
  Future<void> subscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {
    subscribed.add('$serviceUuid:$characteristicUuid');
  }

  @override
  Future<void> unsubscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {}
}

void main() {
  const uuid = 'AA:BB:CC:DD:EE:FF';
  const serviceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
  const charUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';

  final services = [
    BleService(uuid: serviceUuid, characteristicUuids: [charUuid]),
  ];

  late NativeBleTransport transport;

  setUp(() {
    transport = NativeBleTransport(uuid, hostApi: _FakeBleHostApi());
  });

  tearDown(() async {
    await transport.dispose();
  });

  test('a repeated device-ready for a live link keeps existing subscribers streaming', () async {
    BleBridge.instance.onDeviceReady(uuid, services);
    transport.getCharacteristicStream(serviceUuid, charUuid).listen((_) {});

    BleBridge.instance.onPeripheralDisconnected(uuid, null);
    BleBridge.instance.onDeviceReady(uuid, services);

    final received = <List<int>>[];
    final subscription = transport.getCharacteristicStream(serviceUuid, charUuid).listen(received.add);
    addTearDown(subscription.cancel);

    // Native re-emits ready when Dart asks to connect a link that is already up.
    BleBridge.instance.onDeviceReady(uuid, services);
    BleBridge.instance.onCharacteristicValueUpdated(uuid, serviceUuid, charUuid, Uint8List.fromList([1, 2, 3]));
    await Future<void>.delayed(Duration.zero);

    expect(received, [
      [1, 2, 3]
    ]);
  });

  test('device-ready after a disconnect restores the transport to connected', () async {
    BleBridge.instance.onDeviceReady(uuid, services);

    final states = <DeviceTransportState>[];
    final subscription = transport.connectionStateStream.listen(states.add);
    addTearDown(subscription.cancel);

    BleBridge.instance.onPeripheralDisconnected(uuid, null);
    BleBridge.instance.onDeviceReady(uuid, services);
    await Future<void>.delayed(Duration.zero);

    expect(states, [DeviceTransportState.disconnected, DeviceTransportState.connected]);
  });
}
