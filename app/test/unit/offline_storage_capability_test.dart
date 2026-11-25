// Verify that real connector and transport code distinguish absent storage
// from incomplete discovery and failed status reads.
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

const _uuid = 'AA:BB:CC:DD:EE:15';

class _StorageHostApi extends BleHostApi {
  bool connected = true;
  bool readFailed = false;
  Uint8List response = Uint8List(8);
  int reads = 0;

  @override
  Future<bool> isPeripheralConnected(String uuid) async => connected;

  @override
  Future<Uint8List> readCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {
    expect(serviceUuid, storageDataStreamServiceUuid);
    expect(characteristicUuid, storageReadControlCharacteristicUuid);
    reads++;
    if (readFailed) throw StateError('synthetic storage read failure');
    return response;
  }
}

void _advertiseStorage() {
  BleBridge.instance.onDeviceReady(_uuid, [
    BleService(uuid: storageDataStreamServiceUuid, characteristicUuids: [storageReadControlCharacteristicUuid]),
  ]);
}

void main() {
  late _StorageHostApi host;
  late OmiDeviceConnection connection;

  setUp(() {
    host = _StorageHostApi();
    final transport = NativeBleTransport(_uuid, hostApi: host);
    addTearDown(transport.dispose);
    final device = BtDevice(id: _uuid, name: 'Omi CV1', type: DeviceType.omi, rssi: -40);
    connection = OmiDeviceConnection(device, transport);
  });

  test('incomplete native discovery leaves storage unverified', () async {
    expect(await connection.probeOfflineStorageCapability(), OfflineStorageCapability.unverified);
    expect(host.reads, 0);
  });

  test('a complete GATT table with no storage characteristic proves unsupported', () async {
    BleBridge.instance.onDeviceReady(_uuid, [
      BleService(uuid: omiServiceUuid, characteristicUuids: [audioDataStreamCharacteristicUuid]),
    ]);

    expect(await connection.probeOfflineStorageCapability(), OfflineStorageCapability.unsupported);
    expect(host.reads, 0);
  });

  test('present storage with a failed or empty read remains unverified', () async {
    _advertiseStorage();
    host.readFailed = true;
    expect(await connection.probeOfflineStorageCapability(), OfflineStorageCapability.unverified);
    host.readFailed = false;
    host.response = Uint8List(0);
    expect(await connection.probeOfflineStorageCapability(), OfflineStorageCapability.unverified);
    expect(host.reads, 2);
  });

  test('an empty inventory status still confirms supported storage', () async {
    _advertiseStorage();
    expect(await connection.probeOfflineStorageCapability(), OfflineStorageCapability.supported);
    expect(host.reads, 1);
  });

  test('a previously discovered characteristic does not prove a disconnected device is supported', () async {
    _advertiseStorage();
    host.connected = false;
    expect(await connection.probeOfflineStorageCapability(), OfflineStorageCapability.unverified);
    expect(host.reads, 0);
  });
}
