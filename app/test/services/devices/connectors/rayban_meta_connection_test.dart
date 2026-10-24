import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/rayban_meta_transport.dart';

class _FakeRayBanMetaTransport implements RayBanMetaTransport {
  int listeners = 0;
  bool shouldFailAudioStart = false;

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  late final audio = StreamController<List<int>>.broadcast(
    sync: true,
    onListen: () => listeners++,
    onCancel: () => listeners--,
  );

  @override
  Stream<List<int>> getCharacteristicStream(String service, String characteristic) => audio.stream;

  @override
  Future<void> startAudioCapture() async {
    if (shouldFailAudioStart) {
      throw Exception('HFP microphone start failed');
    }
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final device = BtDevice(id: 'rayban-test', name: 'Ray-Ban Meta', type: DeviceType.raybanMeta, rssi: -40);

  test('successful startAudioCapture returns active subscription', () async {
    final transport = _FakeRayBanMetaTransport();
    final connection = RayBanMetaDeviceConnection(device, transport);
    final frames = <List<int>>[];
    final sub = await connection.performGetBleAudioBytesListener(onAudioBytesReceived: frames.add);
    expect(sub, isNotNull);
    expect(transport.listeners, 1);
    transport.audio.add([1, 2, 3]);
    expect(frames, [
      [1, 2, 3]
    ]);
    await sub!.cancel();
    expect(transport.listeners, 0);
  });

  test('failed startAudioCapture cancels subscription and returns null', () async {
    final transport = _FakeRayBanMetaTransport()..shouldFailAudioStart = true;
    final connection = RayBanMetaDeviceConnection(device, transport);
    final frames = <List<int>>[];
    final sub = await connection.performGetBleAudioBytesListener(onAudioBytesReceived: frames.add);
    expect(sub, isNull);
    expect(transport.listeners, 0);
  });
}
