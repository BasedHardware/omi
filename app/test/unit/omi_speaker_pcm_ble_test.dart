import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _SpeakerTransport extends DeviceTransport {
  final notifications = StreamController<List<int>>.broadcast();
  final frames = <List<int>>[];
  int remaining = 0;
  bool autoDrain = true;
  bool failDrain = false;
  int pendingDrain = 0;

  @override
  String get deviceId => 'devkit';
  @override
  Future<void> connect() async {}
  @override
  Future<void> disconnect() async {}
  @override
  Future<bool> isConnected() async => true;
  @override
  Future<bool> ping() async => true;
  @override
  bool hasCharacteristic(String serviceUuid, String characteristicUuid) => true;
  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => notifications.stream;
  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [2];
  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    if (remaining == 0) {
      expect(pendingDrain, 0, reason: 'next frame must wait for DMA completion');
      frames.add(List.of(data));
      remaining = ByteData.sublistView(Uint8List.fromList(data)).getUint32(0, Endian.little);
    } else {
      remaining -= data.length;
      expect(remaining, greaterThanOrEqualTo(0));
      if (remaining == 0) pendingDrain++;
    }
    notifications.add([0x90, 0x01]);
    if (pendingDrain > 0 && autoDrain) drain();
  }

  void drain() {
    pendingDrain--;
    notifications.add([failDrain ? 3 : 2]);
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();
  @override
  Future<void> dispose() => notifications.close();
}

OmiDeviceConnection _connection(_SpeakerTransport transport) => OmiDeviceConnection(
      BtDevice(id: transport.deviceId, name: 'DevKit', type: DeviceType.omi, rssi: -40),
      transport,
    );

Future<void> _until(bool Function() ready) async {
  for (var attempt = 0; attempt < 1000 && !ready(); attempt++) {
    await Future<void>.delayed(const Duration(milliseconds: 1));
  }
  expect(ready(), isTrue);
}

void main() {
  test('v2 two-second reply completes without legacy four-second frame waits', () async {
    final transport = _SpeakerTransport();
    addTearDown(transport.dispose);
    final watch = Stopwatch()..start();
    expect(await _connection(transport).performPlayPcmToSpeaker(Uint8List(32000)), isTrue);
    expect(transport.frames, hasLength(7));
    expect(watch.elapsed, lessThan(const Duration(seconds: 2)));
  });

  test('packet credit alone cannot release the next frame or finish playback', () async {
    final transport = _SpeakerTransport()..autoDrain = false;
    addTearDown(transport.dispose);
    var complete = false;
    final playback = _connection(transport).performPlayPcmToSpeaker(Uint8List(6000)).then((value) {
      complete = true;
      return value;
    });
    await _until(() => transport.pendingDrain == 1);
    expect(transport.frames, hasLength(1));
    expect(complete, isFalse);
    transport.drain();
    await _until(() => transport.frames.length == 2 && transport.pendingDrain == 1);
    expect(complete, isFalse);
    transport.drain();
    expect(await playback, isTrue);
  });

  test('firmware DMA failure fails playback rather than reporting success', () async {
    final transport = _SpeakerTransport()..failDrain = true;
    addTearDown(transport.dispose);
    expect(await _connection(transport).performPlayPcmToSpeaker(Uint8List(800)), isFalse);
  });
}
