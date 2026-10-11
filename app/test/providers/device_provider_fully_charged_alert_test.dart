import 'dart:async';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _NoConnectivityPlatform();
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
    var now = DateTime.utc(2026, 10, 11, 8);
    final provider = _provider(
      transport,
      notifications,
      now: () => now,
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
    now = now.add(const Duration(seconds: 59));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);

    now = now.add(const Duration(seconds: 1));
    provider.onFullyChargedBatterySampleForTesting(66);
    expect(notifications, isEmpty);
    expect(provider.hasFullyChargedAlerted, isFalse);

    now = now.add(const Duration(milliseconds: 1));
    provider.onFullyChargedBatterySampleForTesting(100);
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, [100]);
    expect(provider.hasFullyChargedAlerted, isTrue);

    now = now.add(const Duration(seconds: 1));
    provider.onFullyChargedBatterySampleForTesting(66);
    provider.onFullyChargedBatterySampleForTesting(40);
    expect(notifications, [100]);
    expect(mismatches, [66]);
  });

  test('unplug during dwell drops a later fresh 100', () async {
    final transport = _ChargingTransport();
    final notifications = <int>[];
    var now = DateTime.utc(2026, 10, 11, 8);
    final provider = _provider(transport, notifications, now: () => now);
    addTearDown(transport.notifications.close);
    addTearDown(provider.dispose);
    provider.connectedDevice = _device();

    await provider.initiateChargingStatusListener();
    now = now.add(const Duration(seconds: 10));
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);

    transport.notifications.add([0]);
    expect(provider.isCharging, isFalse);
    expect(provider.fullyChargedChargeStartedAt, isNull);
    expect(provider.hasFullyChargedAlerted, isFalse);

    now = now.add(FullyChargedAlertGate.minimumOnChargerDwell);
    provider.onFullyChargedBatterySampleForTesting(100);
    expect(notifications, isEmpty);
  });
}

BtDevice _device() => BtDevice(id: 'charged-notify', name: 'Omi', type: DeviceType.omi, rssi: -50);

DeviceProvider _provider(
  _ChargingTransport transport,
  List<int> notifications, {
  DateTime Function()? now,
  FullyChargedLevelMismatch? onMismatch,
}) {
  return DeviceProvider(
    chargingConnectionLoader: (_) async => OmiDeviceConnection(_device(), transport),
    clock: now,
    fullyChargedNotification: notifications.add,
    fullyChargedLevelMismatch: onMismatch,
  );
}
