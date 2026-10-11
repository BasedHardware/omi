import 'dart:async';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/fully_charged_alert_gate.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/services.dart';

class _ChargingTransport implements DeviceTransport {
  List<int> value = const [1];
  final notifications = StreamController<List<int>>.broadcast(sync: true);

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    expect(characteristicUuid, OmiDeviceConnection.settingsChargingStatusCharacteristicUuid);
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

/// Firebase-core mock whose initialize response advertises Crashlytics plugin
/// constants, satisfying `FirebaseCrashlyticsPlatform.instanceFor`'s assertion.
class _CrashlyticsCapableFirebaseCore implements TestFirebaseCoreHostApi {
  @override
  Future<PigeonInitializeResponse> initializeApp(String appName, PigeonFirebaseOptions initializeAppRequest) async {
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _NoConnectivityPlatform();
    // onDeviceDisconnected logs to Crashlytics; match the disconnect-telemetry
    // suite's mock app so that path can run without a real Firebase project.
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
      // Ignore if another suite already initialized the singleton.
    }
  });

  test('charging edge with a stale cached 100 does not notify', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    final provider = _provider(transport, notifications);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.batteryLevel = 100;

    await provider.initiateChargingStatusListener();

    expect(provider.isCharging, isTrue);
    expect(provider.fullyChargedChargeStartedAt, isNotNull);
    expect(notifications, isEmpty);
    expect(provider.hasFullyChargedAlerted, isFalse);
  });

  test('fresh 100 after dwell notifies once; 66 after dwell does not', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    final mismatches = <int>[];
    final clock = _Clock();
    final provider = _provider(
      transport,
      notifications,
      now: () => clock.wall,
      monotonicNow: () => clock.mono,
      onMismatch: ({required int notifiedAtLevel, required int correctedLevel}) {
        mismatches.add(correctedLevel);
        expect(notifiedAtLevel, 100);
      },
    );
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.batteryLevel = 100;

    await provider.initiateChargingStatusListener();
    clock.advance(const Duration(seconds: 59));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);

    clock.advance(const Duration(seconds: 1));
    provider.onFullyChargedBatterySampleForTesting(66);
    expect(notifications, isEmpty);
    expect(provider.hasFullyChargedAlerted, isFalse);

    clock.advance(const Duration(milliseconds: 1));
    provider.onFullyChargedBatterySampleForTesting(100);
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100]);
    expect(provider.hasFullyChargedAlerted, isTrue);

    clock.advance(const Duration(seconds: 1));
    provider.onFullyChargedBatterySampleForTesting(66);
    provider.onFullyChargedBatterySampleForTesting(40);
    expect(notifications, [100]);
    expect(mismatches, [66]);
  });

  test('unplug during dwell drops a later fresh 100', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    final clock = _Clock();
    final provider = _provider(transport, notifications, now: () => clock.wall, monotonicNow: () => clock.mono);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();

    await provider.initiateChargingStatusListener();
    clock.advance(const Duration(seconds: 10));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);

    transport.notifications.add([0]);
    expect(provider.isCharging, isFalse);
    expect(provider.fullyChargedChargeStartedAt, isNull);
    expect(provider.hasFullyChargedAlerted, isFalse);

    clock.advance(FullyChargedAlertGate.minimumOnChargerDwell);
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);
  });

  test('device B notifies after device A already alerted when B charges from 66 to 100', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    final clock = _Clock();
    final provider = _provider(transport, notifications, now: () => clock.wall, monotonicNow: () => clock.mono);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);

    provider.connectedDevice = _device('device-a');
    await provider.initiateChargingStatusListener();
    clock.advance(FullyChargedAlertGate.minimumOnChargerDwell + const Duration(milliseconds: 1));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100]);

    provider.onDeviceDisconnected();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    provider.connectedDevice = _device('device-b');
    await provider.initiateChargingStatusListener();
    clock.advance(const Duration(milliseconds: 1));
    provider.onFullyChargedBatterySampleForTesting(66);
    expect(notifications, [100]);

    clock.advance(const Duration(minutes: 30));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100, 100]);
    expect(provider.hasFullyChargedAlerted, isTrue);
  });

  test('same device notifies again when a disconnect hides an unplug and reconnect is below 100', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    final clock = _Clock();
    final provider = _provider(transport, notifications, now: () => clock.wall, monotonicNow: () => clock.mono);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    final device = _device('device-a');
    provider.connectedDevice = device;

    await provider.initiateChargingStatusListener();
    clock.advance(FullyChargedAlertGate.minimumOnChargerDwell + const Duration(milliseconds: 1));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100]);

    provider.onDeviceDisconnected();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    // No charging=false sample: the unplug happened while the link was down.
    provider.connectedDevice = device;
    await provider.initiateChargingStatusListener();
    clock.advance(const Duration(milliseconds: 1));
    provider.onFullyChargedBatterySampleForTesting(66);
    expect(notifications, [100]);
    expect(provider.hasFullyChargedAlerted, isFalse);

    clock.advance(FullyChargedAlertGate.minimumOnChargerDwell);
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100, 100]);
  });

  test('advancing the wall clock does not satisfy fully-charged dwell', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    final clock = _Clock();
    final provider = _provider(transport, notifications, now: () => clock.wall, monotonicNow: () => clock.mono);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();

    await provider.initiateChargingStatusListener();
    clock.advance(const Duration(seconds: 1));
    clock.advanceWall(const Duration(minutes: 2));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);

    clock.advance(FullyChargedAlertGate.minimumOnChargerDwell);
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100]);
  });
}

BtDevice _device([String id = 'charged-notify']) => BtDevice(id: id, name: 'Omi', type: DeviceType.omi, rssi: -50);

class _Clock {
  var wall = DateTime.utc(2026, 10, 11, 8);
  var mono = Duration.zero;

  void advance(Duration duration) {
    wall = wall.add(duration);
    mono += duration;
  }

  void advanceWall(Duration duration) {
    wall = wall.add(duration);
  }
}

DeviceProvider _provider(
  _ChargingTransport transport,
  List<int> notifications, {
  DateTime Function()? now,
  Duration Function()? monotonicNow,
  FullyChargedLevelMismatch? onMismatch,
}) {
  return DeviceProvider(
    chargingConnectionLoader: (_) async => OmiDeviceConnection(_device(), transport),
    clock: now,
    monotonicNow: monotonicNow,
    fullyChargedNotification: notifications.add,
    fullyChargedLevelMismatch: onMismatch,
  );
}
