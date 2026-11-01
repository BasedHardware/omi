import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

/// Answers every read with data, so a test passes only if the capability
/// check consults the advertised characteristics instead of reading.
class _FakeBleHostApi extends BleHostApi {
  int imageReads = 0;

  @override
  Future<bool> isPeripheralConnected(String uuid) async => true;

  @override
  Future<void> manageDevice(String uuid, bool requiresBond) async {}

  @override
  Future<void> subscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {}

  @override
  Future<void> unsubscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {}

  @override
  Future<Uint8List> readCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid) async {
    if (characteristicUuid == imageDataStreamCharacteristicUuid) imageReads++;
    return Uint8List.fromList([1]);
  }
}

/// A non-native transport: absent characteristics throw, as they do there.
class _ThrowingTransport extends DeviceTransport {
  _ThrowingTransport({required this.hasImage});

  final bool hasImage;

  @override
  String get deviceId => 'other-1';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (characteristicUuid == imageDataStreamCharacteristicUuid && !hasImage) {
      throw StateError('characteristic not found');
    }
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

const _uuid = 'AA:BB:CC:DD:EE:01';

BtDevice _device(DeviceType type) => BtDevice(id: _uuid, name: 'Omi', type: type, rssi: -40);

void main() {
  late _FakeBleHostApi host;
  late NativeBleTransport transport;

  setUp(() {
    host = _FakeBleHostApi();
    transport = NativeBleTransport(_uuid, hostApi: host);
  });

  tearDown(() async {
    await transport.dispose();
  });

  void advertise(List<String> characteristics) {
    BleBridge.instance.onDeviceReady(_uuid, [
      BleService(uuid: omiServiceUuid, characteristicUuids: characteristics),
    ]);
  }

  group('photo streaming capability', () {
    test('a pendant without the image characteristic has no camera, whatever a read returns', () async {
      // The native transport answers an absent characteristic with an empty
      // read, not an error; "the read did not throw" counted every pendant as
      // having a camera and the capture loop re-armed photo streaming.
      advertise([audioDataStreamCharacteristicUuid]);
      final connection = OmiDeviceConnection(_device(DeviceType.omi), transport);

      expect(await connection.hasPhotoStreamingCharacteristic(), isFalse);
      expect(host.imageReads, 0, reason: 'the advertised list decides; nothing is read');
    });

    test('glass discovered as an omi device still has a camera', () async {
      // Discovery reports every device as omi; a glass unit whose name lacks
      // "glass" reaches OmiDeviceConnection with that type. The device type
      // cannot be the test.
      advertise([audioDataStreamCharacteristicUuid, imageDataStreamCharacteristicUuid]);
      final connection = OmiDeviceConnection(_device(DeviceType.omi), transport);

      expect(await connection.hasPhotoStreamingCharacteristic(), isTrue);
    });

    test('glass that has not captured yet still has a camera', () async {
      // Glass firmware leaves the image characteristic empty until it
      // captures, and capture starts only after this check says yes.
      advertise([imageDataStreamCharacteristicUuid]);
      final connection = OmiDeviceConnection(_device(DeviceType.openglass), transport);

      expect(await connection.hasPhotoStreamingCharacteristic(), isTrue);
    });

    test('other transports keep reading: an absent characteristic throws there', () async {
      final without = OmiDeviceConnection(_device(DeviceType.omi), _ThrowingTransport(hasImage: false));
      final withImage = OmiDeviceConnection(_device(DeviceType.omi), _ThrowingTransport(hasImage: true));

      expect(await without.hasPhotoStreamingCharacteristic(), isFalse);
      expect(await withImage.hasPhotoStreamingCharacteristic(), isTrue);
    });
  });
}
