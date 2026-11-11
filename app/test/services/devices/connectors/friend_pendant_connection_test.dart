import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/friend_pendant_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _Transport implements DeviceTransport {
  int listeners = 0;
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
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final device = BtDevice(id: 'friend', name: 'Friend', type: DeviceType.friendPendant, rssi: -40);

  test('fake battery emits once with no periodic timer', () {
    fakeAsync((async) {
      final connection = FriendPendantDeviceConnection(device, _Transport());
      final values = <int>[];
      connection.performGetBleBatteryLevelListener(onBatteryLevelChange: values.add);
      async.flushMicrotasks();
      expect(values, [90]);
      async.elapse(const Duration(minutes: 10));
      expect(values, [90]);
      expect(async.periodicTimerCount, 0);
    });
  });

  test('pause unsubscribes the BLE characteristic and resume gets three LC3 frames', () async {
    final transport = _Transport();
    final connection = FriendPendantDeviceConnection(device, transport);
    final frames = <List<int>>[];
    final first = await connection.performGetBleAudioBytesListener(onAudioBytesReceived: frames.add);
    expect(transport.listeners, 1);
    transport.audio.add(List.filled(95, 7));
    expect(frames.map((frame) => frame.length), [30, 30, 30]);
    await first!.cancel();
    expect(transport.listeners, 0);
    final second = await connection.performGetBleAudioBytesListener(onAudioBytesReceived: frames.add);
    expect(transport.listeners, 1);
    await second!.cancel();
    await transport.audio.close();
  });
}
