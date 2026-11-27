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
import 'package:omi/services/devices/battery_display_policy.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/fully_charged_alert_gate.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/services.dart';

class _ChargingTransport implements DeviceTransport {
  List<int> value = const [1];
  List<int> battery = const [3];
  int batteryReads = 0;
  Completer<List<int>>? pendingBattery;
  Completer<List<int>>? pendingRead;
  final notifications = StreamController<List<int>>.broadcast(sync: true);
  final batteryNotifications = StreamController<List<int>>.broadcast(sync: true);

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (characteristicUuid == batteryLevelCharacteristicUuid) {
      batteryReads++;
      if (pendingBattery != null) return pendingBattery!.future;
      return battery;
    }
    expectSync(characteristicUuid, OmiDeviceConnection.settingsChargingStatusCharacteristicUuid);
    if (pendingRead != null) return pendingRead!.future;
    return value;
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) =>
      characteristicUuid == batteryLevelCharacteristicUuid ? batteryNotifications.stream : notifications.stream;

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

  group('battery display guard', _batteryDisplayGuardTests);

  testWidgets('first charge rechecks after settling and keeps the latest reading', (tester) async {
    final pendingStatus = Completer<List<int>>();
    final transport = _ChargingTransport()..pendingRead = pendingStatus;
    final provider = _provider(transport, []);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    provider.batteryLevel = 3;
    provider.prepareFirstChargeCheck(_device().id);
    expect(provider.settingsBatteryLevel, -1);
    final listening = provider.initiateChargingStatusListener();
    await tester.pump(const Duration(seconds: 15));
    expect(transport.batteryReads, 0);
    expect(provider.observedChargingStatus, isNull);
    pendingStatus.complete([1]);
    await listening;
    expect(provider.observedChargingStatus, isTrue);
    await tester.pump(const Duration(seconds: 30));
    expect(transport.batteryReads, 0);

    transport.notifications.add([0]);
    expect(provider.observedChargingStatus, isFalse);
    await tester.pump(const Duration(seconds: 11));
    expect(transport.batteryReads, 0);
    transport.battery = [91];
    await tester.pump(const Duration(seconds: 1));
    expect(transport.batteryReads, 1);
    expect(provider.batteryLevel, 91);
    expect(provider.settingsBatteryLevel, 91);
  });

  testWidgets('a delayed battery read from a retired link is discarded', (tester) async {
    final pending = Completer<List<int>>();
    final transport = _ChargingTransport()
      ..pendingBattery = pending
      ..value = [0];
    final provider = _provider(transport, []);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    provider.prepareFirstChargeCheck(_device().id);
    await provider.initiateChargingStatusListener();
    await tester.pump(const Duration(seconds: 12));
    expect(transport.batteryReads, 1);
    provider.setIsConnected(false);
    expect(provider.observedChargingStatus, isNull);
    pending.complete([91]);
    await tester.pump();
    expect(provider.batteryLevel, -1);
  });

  testWidgets('first-charge failure backs off and a valid zero ends the check', (tester) async {
    final transport = _ChargingTransport()..value = [0];
    final provider = _provider(transport, []);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    final device = _device();
    final finish = provider.prepareFirstChargeCheck(device.id);
    await provider.setConnectedDevice(device);
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    provider.batteryLevel = 3;
    expect(provider.settingsBatteryLevel, -1);
    expect(provider.hasLowBatteryAlertedForTesting, isFalse);
    finish();
    transport.battery = [];
    await tester.pump(const Duration(seconds: 12));
    expect(transport.batteryReads, 1);
    expect(provider.batteryLevel, 3);
    expect(provider.settingsBatteryLevel, -1);
    expect(provider.hasLowBatteryAlertedForTesting, isFalse);
    await tester.pump(const Duration(seconds: 1));
    expect(transport.batteryReads, 1);
    await tester.pump(const Duration(seconds: 1));
    expect(transport.batteryReads, 2);
    transport.battery = [0];
    await tester.pump(const Duration(seconds: 3));
    expect(transport.batteryReads, 2);
    await tester.pump(const Duration(seconds: 1));
    expect(transport.batteryReads, 3);
    expect(provider.settingsBatteryLevel, 0);
    expect(provider.hasLowBatteryAlertedForTesting, isTrue);
    await tester.pump(const Duration(seconds: 9));
    expect(transport.batteryReads, 3);
  });

  testWidgets('missing battery stops retrying after three attempts and accepts a later notification', (tester) async {
    final transport = _ChargingTransport()..battery = [255];
    final provider = _provider(transport, []);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateBleBatteryListener();
    await tester.pump(const Duration(seconds: 2));
    expect(transport.batteryReads, 1);
    await tester.pump(const Duration(seconds: 4));
    expect(transport.batteryReads, 2);
    await tester.pump(const Duration(seconds: 8));
    expect(transport.batteryReads, 3);
    await tester.pump(const Duration(minutes: 1));
    expect(transport.batteryReads, 3);
    expect(provider.settingsBatteryLevel, -1);
    transport.batteryNotifications.add([80]);
    expect(provider.settingsBatteryLevel, 80);
  });

  testWidgets('first-charge retry exhaustion keeps an earlier low sample off Settings', (tester) async {
    final transport = _ChargingTransport()
      ..value = [0]
      ..battery = [];
    final provider = _provider(transport, []);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    provider.batteryLevel = 3;
    provider.prepareFirstChargeCheck(_device().id);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    for (final delay in [12, 2, 4, 8, 30]) {
      await tester.pump(Duration(seconds: delay));
    }
    expect(transport.batteryReads, 4);
    expect(provider.batteryLevel, 3);
    expect(provider.settingsBatteryLevel, -1);
    expect(provider.hasLowBatteryAlertedForTesting, isFalse);

    transport.batteryNotifications.add([80]);
    expect(provider.settingsBatteryLevel, 80);
  });

  testWidgets('charging again drops an in-flight check and restarts the settle wait', (tester) async {
    final pending = Completer<List<int>>();
    final transport = _ChargingTransport()
      ..value = [0]
      ..pendingBattery = pending;
    final provider = _provider(transport, []);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    provider.prepareFirstChargeCheck(_device().id);
    await provider.initiateChargingStatusListener();
    await tester.pump(const Duration(seconds: 12));
    expect(transport.batteryReads, 1);
    transport.notifications.add([1]);
    pending.complete([3]);
    await tester.pump(const Duration(seconds: 30));
    expect(transport.batteryReads, 1);
    expect(provider.settingsBatteryLevel, -1);
    expect(provider.hasLowBatteryAlertedForTesting, isFalse);

    transport.notifications.add([0]);
    transport.pendingBattery = null;
    transport.battery = [90];
    await tester.pump(const Duration(seconds: 12));
    expect(transport.batteryReads, 2);
    expect(provider.settingsBatteryLevel, 90);
  });

  test('late charging read from a disconnected session cannot restore charging', () async {
    final pending = Completer<List<int>>();
    final transport = _ChargingTransport()..pendingRead = pending;
    final provider = _provider(transport, []);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    final device = _device();
    provider.connectedDevice = device;
    provider.batteryLevel = 80;
    final listening = provider.initiateChargingStatusListener();
    // Let the connection loader return so the charging read is in flight.
    await Future<void>.delayed(Duration.zero);
    provider.onDeviceConnectionStateChanged(device.id, DeviceConnectionState.disconnected);
    provider.setIsConnected(true);
    pending.complete([1]);
    await listening;
    expect(provider.batteryLevel, -1);
    expect(provider.isCharging, isFalse);
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

void _batteryDisplayGuardTests() {
  DeviceProvider guarded(_ChargingTransport transport, _Clock clock,
          {bool allowed = true, List<BatteryHideReason>? reported}) =>
      DeviceProvider(
        chargingConnectionLoader: (_) async => OmiDeviceConnection(_device(), transport),
        clock: () => clock.wall,
        monotonicNow: () => clock.mono,
        fullyChargedNotification: (_) {},
        batteryDisplayGuardAllowed: () async => allowed,
        batteryStuckStore: InMemoryBatteryStuckStore(),
        batteryHiddenReporter: reported?.add,
      );

  testWidgets('a low reading while charging shows no percentage until charging stops', (tester) async {
    final transport = _ChargingTransport()..value = [1];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    transport.batteryNotifications.add([1]);
    expect(provider.batteryLevel, 1, reason: 'the raw reading is kept for firmware gating');
    expect(provider.displayBatteryLevel, -1);
    expect(provider.batteryHideReason, BatteryHideReason.chargingLow);
    expect(provider.batteryReadingStuck, isFalse);

    transport.notifications.add([0]);
    transport.batteryNotifications.add([100]);
    expect(provider.displayBatteryLevel, 100);
    expect(provider.batteryHideReason, isNull);
    await tester.pump(const Duration(minutes: 1));
  });

  testWidgets('a flat near-empty reading turns into a stuck reading after ten minutes', (tester) async {
    final transport = _ChargingTransport()..value = [0];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    transport.batteryNotifications.add([1]);
    expect(provider.displayBatteryLevel, 1);

    var notified = 0;
    provider.addListener(() => notified++);
    clock.advance(const Duration(minutes: 10, seconds: 1));
    await tester.pump(const Duration(minutes: 10, seconds: 1));
    expect(provider.displayBatteryLevel, -1);
    expect(provider.batteryHideReason, BatteryHideReason.flat);
    expect(provider.batteryReadingStuck, isTrue);
    expect(notified, greaterThan(0), reason: 'the UI wakes when the reading turns stale');

    transport.batteryNotifications.add([93]);
    expect(provider.displayBatteryLevel, 93);
    expect(provider.batteryReadingStuck, isFalse);
  });

  testWidgets('first pairing hides a stuck near-empty reading and holds the low-battery alert', (tester) async {
    final transport = _ChargingTransport()..value = [0];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    final device = _device();
    final finish = provider.prepareFirstChargeCheck(device.id);
    await provider.setConnectedDevice(device);
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    finish();
    transport.battery = [1];
    await tester.pump(const Duration(seconds: 13));
    expect(provider.batteryLevel, 1);
    expect(provider.displayBatteryLevel, -1);
    expect(provider.settingsBatteryLevel, -1);
    expect(provider.batteryHideReason, BatteryHideReason.firstPairing);
    expect(provider.batteryReadingStuck, isFalse, reason: 'a new pendant may really be empty: no restart advice');
    expect(provider.hasLowBatteryAlertedForTesting, isFalse);
  });

  testWidgets('a near-empty reading defers the low-battery alert until it falls', (tester) async {
    final transport = _ChargingTransport()..value = [0];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    transport.batteryNotifications.add([4]);
    expect(provider.displayBatteryLevel, 4);
    expect(provider.hasLowBatteryAlertedForTesting, isFalse, reason: 'it may still turn out stuck');
    transport.batteryNotifications.add([3]);
    expect(provider.hasLowBatteryAlertedForTesting, isTrue);
    transport.batteryNotifications.add([15]);
    await tester.pump(const Duration(minutes: 11));
  });

  testWidgets('a low first reading stays hidden until the charging status is known', (tester) async {
    final pending = Completer<List<int>>();
    final transport = _ChargingTransport()..pendingRead = pending;
    final clock = _Clock();
    final reported = <BatteryHideReason>[];
    final provider = guarded(transport, clock, reported: reported);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    provider.batteryLevel = 1;
    expect(provider.displayBatteryLevel, -1, reason: '3.0.24 may be on the charger with a frozen 1%');
    final listening = provider.initiateChargingStatusListener();
    pending.complete([1]);
    await listening;
    expect(provider.batteryHideReason, BatteryHideReason.chargingLow);
    expect(reported, [BatteryHideReason.chargingLow]);
  });

  testWidgets('each hide reason is reported once per connection', (tester) async {
    final transport = _ChargingTransport()..value = [1];
    final clock = _Clock();
    final reported = <BatteryHideReason>[];
    final provider = guarded(transport, clock, reported: reported);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    transport.batteryNotifications.add([1]);
    transport.batteryNotifications.add([2]);
    transport.batteryNotifications.add([1]);
    expect(reported, [BatteryHideReason.chargingLow]);
    await tester.pump(const Duration(minutes: 1));
  });

  testWidgets('a falling near-empty reading is real: it shows and alerts', (tester) async {
    final transport = _ChargingTransport()..value = [0];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    final device = _device();
    final finish = provider.prepareFirstChargeCheck(device.id);
    await provider.setConnectedDevice(device);
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    finish();
    transport.battery = [4];
    await tester.pump(const Duration(seconds: 13));
    expect(provider.displayBatteryLevel, -1);
    transport.batteryNotifications.add([3]);
    expect(provider.displayBatteryLevel, 3);
    expect(provider.hasLowBatteryAlertedForTesting, isTrue);
  });

  testWidgets('ordinary percentage changes keep the level throttle', (tester) async {
    final transport = _ChargingTransport()..value = [0];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    transport.batteryNotifications.add([80]);
    var notified = 0;
    provider.addListener(() => notified++);
    transport.batteryNotifications.add([79]);
    expect(provider.displayBatteryLevel, 79);
    expect(notified, 0, reason: 'a one-point change is throttled as before');
  });

  testWidgets('the kill switch shows the pendant reading as reported', (tester) async {
    final transport = _ChargingTransport()..value = [1];
    final clock = _Clock();
    final provider = guarded(transport, clock, allowed: false);
    addTearDown(transport.notifications.close);
    addTearDown(transport.batteryNotifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();
    provider.setIsConnected(true);
    await provider.initiateChargingStatusListener();
    await provider.initiateBleBatteryListener();
    await tester.pump();
    transport.batteryNotifications.add([1]);
    expect(provider.displayBatteryLevel, 1);
    expect(provider.batteryHideReason, isNull);
  });

  testWidgets('non-Omi devices are never guarded', (tester) async {
    final transport = _ChargingTransport()..value = [1];
    final clock = _Clock();
    final provider = guarded(transport, clock);
    addTearDown(provider.dispose);
    provider.connectedDevice = BtDevice(id: 'glass', name: 'OmiGlass', type: DeviceType.openglass, rssi: -50);
    provider.isCharging = true;
    provider.batteryLevel = 1;
    expect(provider.displayBatteryLevel, 1);
  });
}
