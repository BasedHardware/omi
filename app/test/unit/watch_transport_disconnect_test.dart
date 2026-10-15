import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/connectors/apple_watch_connection.dart';
import 'package:omi/services/devices/transports/watch_transport.dart';

class _FakeWatchRecorderHostAPI extends Fake implements WatchRecorderHostAPI {
  int startRecordingCalls = 0;
  int stopRecordingCalls = 0;
  bool shouldThrowOnStop = false;

  @override
  Future<void> startRecording() async {
    startRecordingCalls++;
  }

  @override
  Future<void> stopRecording() async {
    stopRecordingCalls++;
    if (shouldThrowOnStop) {
      throw Exception('WCSession communication error');
    }
  }

  @override
  Future<bool> isWatchSessionSupported() async => true;
}

void main() {
  group('WatchTransport disconnect and dispose recording termination', () {
    test('disconnect calls stopRecording to turn off watch microphone', () async {
      final fakeApi = _FakeWatchRecorderHostAPI();
      final transport = WatchTransport(hostAPI: fakeApi);

      await transport.disconnect();

      expect(fakeApi.stopRecordingCalls, 1);
    });

    test('dispose calls stopRecording to guarantee watch microphone stops on teardown', () async {
      final fakeApi = _FakeWatchRecorderHostAPI();
      final transport = WatchTransport(hostAPI: fakeApi);

      await transport.dispose();

      expect(fakeApi.stopRecordingCalls, 1);
    });

    test('AppleWatchDeviceConnection.disconnect delegates to transport and stops recording', () async {
      final fakeApi = _FakeWatchRecorderHostAPI();
      final transport = WatchTransport(hostAPI: fakeApi);
      final device = BtDevice(id: 'apple-watch', name: 'Apple Watch', type: DeviceType.appleWatch);
      final connection = AppleWatchDeviceConnection(device, transport);

      await connection.disconnect();

      expect(fakeApi.stopRecordingCalls, 1);
    });

    test('disconnect and dispose handle stopRecording errors gracefully (best effort)', () async {
      final fakeApi = _FakeWatchRecorderHostAPI()..shouldThrowOnStop = true;
      final transport = WatchTransport(hostAPI: fakeApi);

      // Must not rethrow or crash caller
      await transport.disconnect();
      await transport.dispose();

      expect(fakeApi.stopRecordingCalls, 2);
    });
  });
}
