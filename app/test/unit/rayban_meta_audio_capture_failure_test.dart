import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/transports/rayban_meta_transport.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/enums.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

class _NoopLocationCapture extends ConversationLocationCapture {
  @override
  Future<Geolocation?> captureAndUpload({bool promptIfDenied = true}) async => null;

  @override
  Future<Geolocation?> capture({bool promptIfDenied = true}) async => null;

  @override
  Future<void> uploadCompatibilitySnapshot(Geolocation geolocation) async {}
}

class _MockRayBanMetaTransport extends RayBanMetaTransport {
  _MockRayBanMetaTransport(super.deviceId, {required this.audioStream, this.shouldFailStart = false});

  final Stream<List<int>> audioStream;
  bool shouldFailStart;
  bool startAudioCaptureCalled = false;

  @override
  Future<bool> isConnected() async => true;

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

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return Directory.systemTemp.path;
        return null;
      },
    );
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
    try {
      await ServiceManager.init();
    } catch (_) {}
  });

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

      await expectLater(
        connection.performGetBleAudioBytesListener(onAudioBytesReceived: (_) {}),
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

  group('CaptureController Ray-Ban Meta start and resume guards', () {
    test('streamDeviceRecording stays stopped and emits capture_unavailable when startAudioCapture fails', () async {
      final audioController = StreamController<List<int>>.broadcast();
      addTearDown(audioController.close);

      SharedPreferencesUtil().batchModeEnabled = true;
      addTearDown(() => SharedPreferencesUtil().batchModeEnabled = false);

      final transport = _MockRayBanMetaTransport('meta-1', audioStream: audioController.stream, shouldFailStart: true);
      final device = BtDevice(
        id: 'meta-1',
        name: 'Ray-Ban Meta',
        type: DeviceType.raybanMeta,
        rssi: -40,
        locator: DeviceLocator.metaDat(),
      );
      final connection = RayBanMetaDeviceConnection(device, transport);

      final events = <({String name, Map<String, dynamic> properties})>[];
      final telemetry = RecordingLifecycleTelemetry(
        emitter: (name, properties) => events.add((name: name, properties: properties)),
        idFactory: () => 'recording-rayban-fail',
      );
      final provider = CaptureProvider(
        recordingTelemetry: telemetry,
        deviceConnectionLoader: (_) async => connection,
        audioCodecLoader: (_) async => BleAudioCodec.pcm16,
        inProgressConversationLoader: () async {},
        conversationLocationCapture: _NoopLocationCapture(),
      );
      addTearDown(provider.dispose);

      await provider.streamDeviceRecording(device: device);

      expect(transport.startAudioCaptureCalled, isTrue);
      expect(audioController.hasListener, isFalse);
      expect(provider.recordingState, isNot(RecordingState.deviceRecord));
      expect(
        events.map((event) => event.name),
        [RecordingLifecycleTelemetry.requestedEvent, RecordingLifecycleTelemetry.startFailedEvent],
      );
      expect(events.last.properties['failure_class'], 'capture_unavailable');
    });

    test('resumeDeviceRecording keeps RecordingState.pause when startAudioCapture fails on resume', () async {
      final audioController = StreamController<List<int>>.broadcast();
      addTearDown(audioController.close);

      SharedPreferencesUtil().batchModeEnabled = true;
      addTearDown(() => SharedPreferencesUtil().batchModeEnabled = false);

      final transport = _MockRayBanMetaTransport('meta-1', audioStream: audioController.stream, shouldFailStart: false);
      final device = BtDevice(
        id: 'meta-1',
        name: 'Ray-Ban Meta',
        type: DeviceType.raybanMeta,
        rssi: -40,
        locator: DeviceLocator.metaDat(),
      );
      final connection = RayBanMetaDeviceConnection(device, transport);

      final provider = CaptureProvider(
        deviceConnectionLoader: (_) async => connection,
        audioCodecLoader: (_) async => BleAudioCodec.pcm16,
        inProgressConversationLoader: () async {},
        conversationLocationCapture: _NoopLocationCapture(),
      );
      addTearDown(provider.dispose);

      await provider.streamDeviceRecording(device: device);
      expect(provider.recordingState, RecordingState.deviceRecord);
      expect(audioController.hasListener, isTrue);

      await provider.pauseDeviceRecording();
      expect(provider.recordingState, RecordingState.pause);
      expect(audioController.hasListener, isFalse);

      transport.shouldFailStart = true;
      transport.startAudioCaptureCalled = false;

      await provider.resumeDeviceRecording();
      expect(transport.startAudioCaptureCalled, isTrue);
      expect(audioController.hasListener, isFalse);
      expect(provider.recordingState, RecordingState.pause);
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
