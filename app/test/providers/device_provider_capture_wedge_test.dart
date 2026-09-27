import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/enums.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

class _StubCaptureProvider implements CaptureProvider {
  BtDevice? device;
  RecordingState state = RecordingState.stop;
  bool paused = false;

  @override
  BtDevice? get recordingDevice => device;

  @override
  RecordingState get recordingState => state;

  @override
  bool get isPaused => paused;

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _StubLocalRecordingsProvider implements LocalRecordingsProvider {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {}
  });

  List<({String event, Map<String, Object> properties})> events = [];

  CaptureWedgeMonitor makeMonitor() {
    return CaptureWedgeMonitor(
      featureGate: () async => true,
      track: (event, properties) => events.add((event: event, properties: properties)),
      bleRetry: (_) async {},
      appBuild: () => '1',
      platform: () => 'ios',
    );
  }

  DeviceProvider makeProvider(
    CaptureWedgeMonitor monitor, {
    List<String>? diagnosticsCalls,
  }) {
    return DeviceProvider(
      captureWedgeMonitor: monitor,
      bleDiagnosticsLoader: (deviceId) async {
        diagnosticsCalls?.add(deviceId);
        return BleDeviceDiagnostics(
          disconnectHistory: const [],
          nativeBackgroundBytesConsumed: 0,
          nativeBackgroundPacketsConsumed: 0,
          reconnectionCount: 0,
          connectedAt: 0,
          failToConnectCount: 0,
        );
      },
    );
  }

  BtDevice pendant() => BtDevice(
        id: 'AA:BB:CC:DD:EE:01',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -50,
        firmwareRevision: '3.0.20',
      );

  Future<void> flap(DeviceProvider provider, BtDevice device, {int times = 3}) async {
    for (var i = 0; i < times; i++) {
      await provider.setConnectedDevice(device);
      await provider.setConnectedDevice(null);
    }
  }

  setUp(() => events = []);

  tearDown(() {
    SharedPreferencesUtil().batchModeEnabled = false;
  });

  test('rapid BLE drops of a live device-capture pendant declare a wedge', () async {
    final monitor = makeMonitor();
    final provider = makeProvider(monitor);
    addTearDown(provider.dispose);
    final capture = _StubCaptureProvider();
    provider.setProviders(capture, _StubLocalRecordingsProvider());
    final device = pendant();
    capture.device = device;
    capture.state = RecordingState.deviceRecord;

    await flap(provider, device);
    await pumpEventQueue();

    final detected = events.where((e) => e.event == 'Capture Wedge Detected').toList();
    expect(detected, hasLength(1));
    expect(detected.single.properties['trigger'], 'rapid_reconnects');
  });

  test('rapid drops while the phone mic owns capture do not count', () async {
    final monitor = makeMonitor();
    final provider = makeProvider(monitor);
    addTearDown(provider.dispose);
    final capture = _StubCaptureProvider();
    provider.setProviders(capture, _StubLocalRecordingsProvider());
    final device = pendant();
    capture.device = device;
    capture.state = RecordingState.record;

    await flap(provider, device);
    await pumpEventQueue();

    expect(events.where((e) => e.event == 'Capture Wedge Detected'), isEmpty);
  });

  test('rapid drops with no live capture do not count', () async {
    final monitor = makeMonitor();
    final provider = makeProvider(monitor);
    addTearDown(provider.dispose);
    provider.setProviders(_StubCaptureProvider(), _StubLocalRecordingsProvider());
    final device = pendant();

    await flap(provider, device);
    await pumpEventQueue();

    expect(events.where((e) => e.event == 'Capture Wedge Detected'), isEmpty);
  });

  test('rapid drops while capture is paused do not count', () async {
    final monitor = makeMonitor();
    final provider = makeProvider(monitor);
    addTearDown(provider.dispose);
    final capture = _StubCaptureProvider();
    provider.setProviders(capture, _StubLocalRecordingsProvider());
    final device = pendant();
    capture.device = device;
    capture.state = RecordingState.deviceRecord;
    capture.paused = true;

    await flap(provider, device);
    await pumpEventQueue();

    expect(events.where((e) => e.event == 'Capture Wedge Detected'), isEmpty);
  });

  test('rapid drops in batch mode do not count', () async {
    final monitor = makeMonitor();
    final provider = makeProvider(monitor);
    addTearDown(provider.dispose);
    final capture = _StubCaptureProvider();
    provider.setProviders(capture, _StubLocalRecordingsProvider());
    final device = pendant();
    capture.device = device;
    capture.state = RecordingState.deviceRecord;
    SharedPreferencesUtil().batchModeEnabled = true;

    await flap(provider, device);
    await pumpEventQueue();

    expect(events.where((e) => e.event == 'Capture Wedge Detected'), isEmpty);
  });

  test('markDisconnectIntentional dismisses a visible wedge prompt for that device', () async {
    final monitor = makeMonitor();
    final provider = makeProvider(monitor);
    addTearDown(provider.dispose);
    final capture = _StubCaptureProvider();
    provider.setProviders(capture, _StubLocalRecordingsProvider());
    final device = pendant();
    capture.device = device;
    capture.state = RecordingState.deviceRecord;

    await flap(provider, device);
    await pumpEventQueue();
    expect(monitor.visiblePrompt, isNotNull);

    provider.markDisconnectIntentional(device.id);
    expect(monitor.visiblePrompt, isNull);
  });

  test('ended sessions without live capture still run diagnostics', () async {
    final monitor = makeMonitor();
    final diagnosticsCalls = <String>[];
    final provider = makeProvider(monitor, diagnosticsCalls: diagnosticsCalls);
    addTearDown(provider.dispose);
    provider.setProviders(_StubCaptureProvider(), _StubLocalRecordingsProvider());
    final device = pendant();

    await provider.setConnectedDevice(device);
    await provider.setConnectedDevice(null);
    await pumpEventQueue();

    expect(diagnosticsCalls, [device.id]);
    expect(events.where((e) => e.event == 'Capture Wedge Detected'), isEmpty);
  });
}
