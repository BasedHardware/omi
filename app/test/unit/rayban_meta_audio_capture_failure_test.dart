import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/rayban_meta_transport.dart';

class _MockRayBanMetaTransport extends RayBanMetaTransport {
  _MockRayBanMetaTransport(super.deviceId, {required this.audioStream, this.shouldFailStart = false});

  final Stream<List<int>> audioStream;
  final bool shouldFailStart;
  bool startAudioCaptureCalled = false;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    if (serviceUuid == rayBanMetaAudioServiceUuid && characteristicUuid == rayBanMetaAudioDataCharacteristicUuid) {
      return audioStream;
    }
    return const Stream.empty();
  }

  @override
  Future<void> startAudioCapture() async {
    startAudioCaptureCalled = true;
    if (shouldFailStart) {
      throw StateError('Audio capture start failed: hardware busy');
    }
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RayBanMetaDeviceConnection audio capture start failure', () {
    test('cancels subscription and rethrows when startAudioCapture fails', () async {
      final audioController = StreamController<List<int>>.broadcast();
      addTearDown(audioController.close);

      final transport = _MockRayBanMetaTransport('meta-1', audioStream: audioController.stream, shouldFailStart: true);
      final device = BtDevice(
        id: 'meta-1',
        name: 'Ray-Ban Meta',
        type: DeviceType.raybanMeta,
        rssi: -40,
        locator: DeviceLocator.metaDat(),
      );
      final connection = RayBanMetaDeviceConnection(device, transport);

      expect(audioController.hasListener, isFalse);

      expect(
        () => connection.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {}),
        throwsA(isA<StateError>().having((e) => e.message, 'message', contains('Audio capture start failed'))),
      );

      // Subscription should be cancelled after rethrow
      expect(audioController.hasListener, isFalse);
      expect(transport.startAudioCaptureCalled, isTrue);
    });

    test('returns active subscription when startAudioCapture succeeds', () async {
      final audioController = StreamController<List<int>>.broadcast();
      addTearDown(audioController.close);

      final transport = _MockRayBanMetaTransport('meta-1', audioStream: audioController.stream, shouldFailStart: false);
      final device = BtDevice(
        id: 'meta-1',
        name: 'Ray-Ban Meta',
        type: DeviceType.raybanMeta,
        rssi: -40,
        locator: DeviceLocator.metaDat(),
      );
      final connection = RayBanMetaDeviceConnection(device, transport);

      final subscription = await connection.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {});

      expect(subscription, isNotNull);
      expect(audioController.hasListener, isTrue);
      expect(transport.startAudioCaptureCalled, isTrue);

      await subscription!.cancel();
      expect(audioController.hasListener, isFalse);
    });
  });

  group('CaptureWedgeMonitor rayban_meta scoping', () {
    test('isCaptureSourceInScope admits rayban_meta', () {
      expect(CaptureWedgeMonitor.isCaptureSourceInScope('rayban_meta'), isTrue);
      expect(CaptureWedgeMonitor.isCaptureSourceInScope('omi'), isTrue);
      expect(CaptureWedgeMonitor.isCaptureSourceInScope('friend_com'), isTrue);
      expect(CaptureWedgeMonitor.isCaptureSourceInScope('phone'), isFalse);
      expect(CaptureWedgeMonitor.isCaptureSourceInScope('openglass'), isFalse);
    });
  });
}
