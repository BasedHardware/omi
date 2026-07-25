import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _FakeOmiTransport extends DeviceTransport {
  final _audio = StreamController<List<int>>.broadcast();
  final _state = StreamController<DeviceTransportState>.broadcast();

  void emitAudio(List<int> packet) => _audio.add(packet);

  @override
  String get deviceId => 'fake-omi';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<void> dispose() async {
    await _audio.close();
    await _state.close();
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => _audio.stream;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _state.stream;

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => const [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Omi audio binding suppresses only malformed and exact adjacent duplicates', () async {
    final transport = _FakeOmiTransport();
    final device = BtDevice(name: 'Omi', id: 'fake-omi', type: DeviceType.omi, rssi: -50);
    final connection = OmiDeviceConnection(device, transport);
    final received = <List<int>>[];
    final subscription = await connection.performGetBleAudioBytesListener(onAudioBytesReceived: received.add);
    const first = [10, 0, 0, 0xAA];
    const sameIdDifferentIndex = [10, 0, 1, 0xBB];

    transport.emitAudio(first);
    transport.emitAudio(first);
    transport.emitAudio(sameIdDifferentIndex);
    transport.emitAudio([1, 2]);
    transport.emitAudio([11, 0, 0, 0xCC]);
    await pumpEventQueue();

    expect(received, [
      first,
      sameIdDifferentIndex,
      [11, 0, 0, 0xCC]
    ]);

    await subscription?.cancel();
    await connection.disconnect();
    await transport.dispose();
  });
}
