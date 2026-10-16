import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/bee_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _TestTransport extends DeviceTransport {
  @override
  String get deviceId => 'test-bee-device';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String s, String c) => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String s, String c) async => [];

  @override
  Future<void> writeCharacteristic(String s, String c, List<int> d) async {}

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
}

BtDevice _testDevice() => BtDevice(id: 'test-bee-device', name: 'Bee Test', type: DeviceType.bee, rssi: -40);

void main() {
  group('BeeDeviceConnection.parseBatteryResponse', () {
    late BeeDeviceConnection connection;

    setUp(() {
      connection = BeeDeviceConnection(_testDevice(), _TestTransport());
    });

    test('returns null for payloads shorter than 2 bytes', () {
      expect(connection.parseBatteryResponse([]), isNull);
      expect(connection.parseBatteryResponse([0xdb]), isNull);
    });

    test('parses legacy 2-byte percentage payload correctly', () {
      final res = connection.parseBatteryResponse([85, 0]);
      expect(res, isNotNull);
      expect(res!['level'], 85);
      expect(res['is_charging'], false);

      final chargingRes = connection.parseBatteryResponse([100, 1]);
      expect(chargingRes, isNotNull);
      expect(chargingRes!['level'], 100);
      expect(chargingRes['is_charging'], true);
    });

    test('clamps legacy 2-byte percentage values to 0-100 range', () {
      final overRes = connection.parseBatteryResponse([150, 0]);
      expect(overRes!['level'], 100);
    });

    test('parses 3-byte voltage payload (Bee Frontier 4059 mV sample from issue #21749)', () {
      // 0xdb, 0x0f -> 0x0fdb = 4059 mV, state 0 (not charging)
      final res = connection.parseBatteryResponse([0xdb, 0x0f, 0x00]);
      expect(res, isNotNull);
      expect(res!['level'], 77);
      expect(res['is_charging'], false);

      // Same voltage when charging
      final chargingRes = connection.parseBatteryResponse([0xdb, 0x0f, 0x01]);
      expect(chargingRes, isNotNull);
      expect(chargingRes!['level'], 62);
      expect(chargingRes['is_charging'], true);
    });

    test('parses 3-byte boundary voltages correctly', () {
      // 4200 mV (0x1068) full battery
      final fullRes = connection.parseBatteryResponse([0x68, 0x10, 0x00]);
      expect(fullRes!['level'], 100);
      expect(fullRes['is_charging'], false);

      // 3400 mV (0x0d48) empty battery
      final emptyRes = connection.parseBatteryResponse([0x48, 0x0d, 0x00]);
      expect(emptyRes!['level'], 0);
      expect(emptyRes['is_charging'], false);
    });

    test('rejects implausible voltage readings below 3000 mV or above 4500 mV', () {
      // 1280 mV (0x0500) - garbage or non-battery reading
      expect(connection.parseBatteryResponse([0x00, 0x05, 0x00]), isNull);

      // 5120 mV (0x1400) - exceeds max LiPo limit
      expect(connection.parseBatteryResponse([0x00, 0x14, 0x00]), isNull);
    });
  });
}
