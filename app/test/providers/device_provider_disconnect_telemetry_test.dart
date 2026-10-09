import 'dart:async';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _RecordingAdapter implements AnalyticsAdapter {
  final events = <String>[];
  final properties = <Map<String, Object>>[];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(eventName);
    this.properties.add(Map.of(properties ?? {}));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _CaptureIntent extends ChangeNotifier implements CaptureProvider {
  int cleared = 0;
  int chargeStarts = 0;
  @override
  void onChargingStarted() => chargeStarts++;
  @override
  void updateRecordingDevice(BtDevice? device) {
    if (device == null) cleared++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _ChargingTransport implements DeviceTransport {
  List<int> value = [1];
  bool failRead = false;
  final notifications = StreamController<List<int>>.broadcast(sync: true);

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    expect(characteristicUuid, OmiDeviceConnection.settingsChargingStatusCharacteristicUuid);
    if (failRead) throw StateError('GATT read failed');
    return value;
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) => notifications.stream;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _NoConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

BtDevice _device(String id) => BtDevice(id: id, name: 'Omi', type: DeviceType.omi, rssi: -50);

/// Firebase-core mock whose initialize response advertises Crashlytics plugin
/// constants, satisfying `FirebaseCrashlyticsPlatform.instanceFor`'s assertion.
class _CrashlyticsCapableFirebaseCore implements TestFirebaseCoreHostApi {
  @override
  Future<PigeonInitializeResponse> initializeApp(
    String appName,
    PigeonFirebaseOptions initializeAppRequest,
  ) async {
    return PigeonInitializeResponse(
      name: appName,
      options: initializeAppRequest,
      pluginConstants: {
        'plugins.flutter.io/firebase_crashlytics': {'isCrashlyticsCollectionEnabled': true},
      },
    );
  }

  @override
  Future<List<PigeonInitializeResponse?>> initializeCore() async => [];

  @override
  Future<PigeonFirebaseOptions> optionsFromResource() async => throw UnimplementedError();
}

BleDisconnectEvent _persistedEvent({
  required int timestamp,
  String reason = 'connection_timeout',
  int reasonCode = 8,
  String appState = 'background',
}) {
  return BleDisconnectEvent(
    timestamp: timestamp,
    reason: reason,
    reasonCode: reasonCode,
    isManual: false,
    eventType: 'disconnect',
    lastRssi: -82,
    connectionDurationMs: 1250,
    appState: appState,
    timeToReconnectMs: 0,
    rssiTrend: 'sudden',
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _NoConnectivityPlatform();
    // onDeviceDisconnected logs to Crashlytics before tracking; give Firebase
    // a mock app whose plugin constants satisfy the Crashlytics platform
    // assertion, and a no-op Crashlytics method channel.
    TestFirebaseCoreHostApi.setup(_CrashlyticsCapableFirebaseCore());
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/firebase_crashlytics'),
      (call) async => null,
    );
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: const FirebaseOptions(
          apiKey: 'fake',
          appId: '1:1:ios:fake',
          messagingSenderId: '1',
          projectId: 'demo-omi-local',
        ),
      );
    }
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  tearDown(AnalyticsManager.resetForTesting);

  for (final emptyRead in [false, true]) {
    for (final recoverViaNotify in [false, true]) {
      test('unknown charging read preserves edge history (empty=$emptyRead, notify=$recoverViaNotify)', () async {
        final transport = _ChargingTransport();
        final device = _device('charging-device');
        final connection = OmiDeviceConnection(device, transport);
        final capture = _CaptureIntent();
        final provider = DeviceProvider(chargingConnectionLoader: (_) async => connection);
        addTearDown(transport.notifications.close);
        addTearDown(provider.dispose);
        addTearDown(capture.dispose);
        provider.captureProvider = capture;
        provider.connectedDevice = device;

        // Seed a successful charging observation before the session is paused.
        await provider.initiateChargingStatusListener(allowCaptureResume: false);
        expect(provider.isCharging, true);
        expect(capture.chargeStarts, 0);

        transport.failRead = !emptyRead;
        transport.value = [];
        await provider.initiateChargingStatusListener();
        expect(provider.isCharging, true, reason: 'unknown does not replace the last known UI state');
        expect(capture.chargeStarts, 0);

        if (recoverViaNotify) {
          transport.notifications.add([]);
          transport.notifications.add([1]);
        } else {
          transport.failRead = false;
          transport.value = [1];
          await provider.initiateChargingStatusListener();
        }
        expect(capture.chargeStarts, 0, reason: 'a failed read must not fabricate an unplug/replug edge');
      });
    }
  }

  test('authorized first charging notification retains its edge during a later sync scope', () async {
    final transport = _ChargingTransport()..failRead = true;
    final device = _device('later-sync-charge');
    final connection = OmiDeviceConnection(device, transport);
    final capture = _CaptureIntent();
    final provider = DeviceProvider(chargingConnectionLoader: (_) async => connection)
      ..connectedDevice = device
      ..captureProvider = capture;
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    addTearDown(capture.dispose);
    await provider.initiateChargingStatusListener(allowCaptureResume: true);
    await SyncWakeScope.run(() async {
      transport.notifications.add([1]);
      expect(capture.chargeStarts, 1);
      transport.notifications.add([1]);
      expect(capture.chargeStarts, 1);
      transport.notifications.add([0]);
      transport.notifications.add([1]);
      expect(capture.chargeStarts, 2);
    });
  });

  for (final origin in ['gated connect', 'sync notify', 'notify after sync', 'ordinary connect']) {
    for (final firstCharging in [false, true]) {
      test('first notify after failed read respects $origin gate (charging=$firstCharging)', () async {
        final transport = _ChargingTransport()..failRead = true;
        final device = _device('charging-notify-device');
        final connection = OmiDeviceConnection(device, transport);
        final capture = _CaptureIntent();
        final provider = DeviceProvider(chargingConnectionLoader: (_) async => connection);
        addTearDown(transport.notifications.close);
        addTearDown(provider.dispose);
        addTearDown(capture.dispose);
        provider.captureProvider = capture;
        provider.connectedDevice = device;

        void notifyInitial() {
          transport.notifications.add([]); // No observation yet.
          transport.notifications.add([firstCharging ? 1 : 0]);
          expect(provider.isCharging, firstCharging);
          expect(capture.chargeStarts, origin == 'ordinary connect' && firstCharging ? 1 : 0);
          // Repeated snapshots must not create another edge.
          transport.notifications.add([firstCharging ? 1 : 0]);
        }

        if (origin == 'sync notify' || origin == 'notify after sync') {
          await SyncWakeScope.run(() async {
            await provider.initiateChargingStatusListener();
            if (origin == 'sync notify') notifyInitial();
          });
          if (origin == 'notify after sync') notifyInitial();
        } else {
          await provider.initiateChargingStatusListener(allowCaptureResume: origin == 'ordinary connect');
          notifyInitial();
        }
        final started = capture.chargeStarts;
        transport.notifications.add([0]);
        transport.notifications.add([1]);
        expect(capture.chargeStarts, started + 1, reason: 'later genuine charge-start still resumes');
        transport.notifications.add([1]);
        expect(capture.chargeStarts, started + 1);
      });
    }
  }

  test('first charging sample resumes once, clean reconnect and steady samples do not', () async {
    final transport = _ChargingTransport();
    final device = _device('charging-device');
    final connection = OmiDeviceConnection(device, transport);
    final capture = _CaptureIntent();
    final provider = DeviceProvider(
      chargingConnectionLoader: (_) async => connection,
      bleDiagnosticsLoader: (_) async => throw StateError('no diagnostics'),
    );
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    addTearDown(capture.dispose);
    provider.captureProvider = capture;
    provider.connectedDevice = device;
    await provider.initiateChargingStatusListener();
    expect(capture.chargeStarts, 1);
    transport.notifications.add([1]);
    expect(capture.chargeStarts, 1);

    provider.onDeviceDisconnected();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    provider.connectedDevice = device;
    await provider.initiateChargingStatusListener();
    expect(capture.chargeStarts, 1, reason: 'clean link loss does not forget a successful observation');
    transport.notifications.add([0]);
    transport.notifications.add([1]);
    expect(capture.chargeStarts, 2, reason: 'a real unplug and replug remains a resume trigger');
  });

  test('disconnect emits Device Disconnected Detailed from the freshest persisted event', () async {
    final analytics = _RecordingAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    final now = DateTime.now().millisecondsSinceEpoch;
    final provider = DeviceProvider(
      bleDiagnosticsLoader: (_) async => BleDeviceDiagnostics(
        disconnectHistory: [
          _persistedEvent(
              timestamp: now - 3600 * 1000, reason: 'clean_disconnect', reasonCode: 0, appState: 'foreground'),
          _persistedEvent(timestamp: now - 1000, reason: 'gatt_error_25', reasonCode: 25, appState: 'inactive'),
        ],
        reconnectionCount: 3,
        connectedAt: 0,
        failToConnectCount: 0,
        nativeBackgroundBytesConsumed: 0,
        nativeBackgroundPacketsConsumed: 0,
      ),
    );
    addTearDown(provider.dispose);
    provider.pairedDevice = _device('AA:AA:AA:AA:AA:10');
    provider.connectedDevice = provider.pairedDevice;

    // The provider fires tracking unawaited; drain its microtask chain before flushing.
    provider.onDeviceDisconnected();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await AnalyticsManager.flushPending(force: true);

    final emitted = [
      for (var i = 0; i < analytics.events.length; i++)
        if (analytics.events[i] == 'Device Disconnected Detailed') analytics.properties[i],
    ];
    expect(emitted, hasLength(1));
    // The freshest persisted event carries the reported reason, not the older one.
    expect(emitted.single, containsPair('reason', 'gatt_error'));
    expect(emitted.single, containsPair('reason_code', 25));
    expect(emitted.single, containsPair('app_state', 'inactive'));
    // The deprecated property-less emission must not dual-fire.
    expect(analytics.events.where((event) => event == 'Device Disconnected'), isEmpty);
  });

  for (final recovery in [true, false]) {
    test('physical disconnect preserves capture intent only for recovery=$recovery', () async {
      const id = 'AA:AA:AA:AA:AA:12';
      final capture = _CaptureIntent();
      final provider = DeviceProvider(bleDiagnosticsLoader: (_) async => throw StateError('no diagnostics'));
      addTearDown(provider.dispose);
      addTearDown(capture.dispose);
      addTearDown(() => BleBridge.instance.unregisterPeripheral(id));
      provider.captureProvider = capture;
      provider.pairedDevice = _device(id);
      BleBridge.instance.onPeripheralDisconnected(id, recovery ? 'capture_recovery' : null);
      provider.onDeviceDisconnected();
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(provider.connectedDevice, isNull);
      expect(capture.cleared, recovery ? 0 : 1);
    });
  }

  test('unreadable diagnostics still emit with unknown reason fields', () async {
    final analytics = _RecordingAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    final provider = DeviceProvider(
      bleDiagnosticsLoader: (_) async => throw StateError('native channel unavailable'),
    );
    addTearDown(provider.dispose);
    provider.pairedDevice = _device('AA:AA:AA:AA:AA:11');

    // The provider fires tracking unawaited; drain its microtask chain before flushing.
    provider.onDeviceDisconnected();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await AnalyticsManager.flushPending(force: true);

    final emitted = [
      for (var i = 0; i < analytics.events.length; i++)
        if (analytics.events[i] == 'Device Disconnected Detailed') analytics.properties[i],
    ];
    expect(emitted, hasLength(1));
    expect(emitted.single, containsPair('reason', 'unknown'));
    expect(emitted.single, containsPair('reason_code', -1));
    expect(emitted.single, containsPair('app_state', 'unknown'));
  });
}
