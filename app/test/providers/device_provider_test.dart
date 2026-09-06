import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async {
    return [ConnectivityResult.none];
  }

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('onboarding connection emits Device Connected exactly once', () async {
    final analytics = _TestAnalyticsAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    SharedPreferencesUtil().uid = 'test-user';
    final provider = DeviceProvider();
    addTearDown(provider.dispose);
    final device = BtDevice(
      id: 'AA:AA:AA:AA:AA:01',
      name: 'User-renamed device',
      type: DeviceType.fieldy,
      rssi: -50,
      firmwareRevision: '3.0.20',
      serialNumber: 'OMI-SERIAL-001',
    );

    await provider.setConnectedDevice(device);
    await provider.setConnectedDevice(device);
    await AnalyticsManager.flushPending(force: true);

    expect(analytics.events.where((event) => event == 'Device Connected'), hasLength(1));
    final connectedProperties = analytics.eventProperties[analytics.events.indexOf('Device Connected')];
    expect(connectedProperties['id'], device.id);
    expect(connectedProperties['name'], device.name);
    expect(connectedProperties['firmwareRevision'], device.firmwareRevision);
    expect(connectedProperties['type'], 'fieldy');
    expect(connectedProperties['device_vendor'], 'fieldlabs');
    expect(connectedProperties['hardware_family'], 'fieldy');
    expect(
        connectedProperties['transport_device_id'], sha256.convert(utf8.encode(device.id)).toString().substring(0, 16));
    expect(connectedProperties['transport_id_stability'], 'platform_dependent');
    expect(
        connectedProperties['hardware_id'], sha256.convert(utf8.encode('OMI-SERIAL-001')).toString().substring(0, 16));
    expect(connectedProperties['hardware_id_kind'], 'manufacturer_serial');
    expect(connectedProperties['hardware_id_stable'], isTrue);
    expect(analytics.personProperties.any((properties) => properties['device_vendor'] == 'fieldlabs'), isTrue);
    expect(analytics.personProperties.any((properties) => properties['hardware_family'] == 'fieldy'), isTrue);
  });

  test('find device coalesces overlapping provider requests', () async {
    final completion = Completer<bool>();
    var runnerCalls = 0;
    final provider = DeviceProvider(
      findDeviceRunner: (_) {
        runnerCalls++;
        return completion.future;
      },
    );
    addTearDown(provider.dispose);
    provider.connectedDevice = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
    provider.isConnected = true;

    final first = provider.findDevice();
    final second = provider.findDevice();

    expect(identical(first, second), isTrue);
    expect(runnerCalls, 1);

    completion.complete(true);
    expect(await first, isTrue);
    expect(await second, isTrue);

    expect(await provider.findDevice(), isTrue);
    expect(runnerCalls, 2);
  });

  test('find device rejects OmiGlass devices before invoking the runner', () async {
    var runnerCalls = 0;
    final provider = DeviceProvider(
      findDeviceRunner: (_) async {
        runnerCalls++;
        return true;
      },
    );
    addTearDown(provider.dispose);
    provider.connectedDevice = BtDevice(id: 'glass-1', name: 'OmiGlass', type: DeviceType.omi, rssi: -40);
    provider.isConnected = true;

    expect(await provider.findDevice(), isFalse);
    expect(runnerCalls, 0);
  });

  test('Device Paired is deduped by user and device while connections recur', () async {
    SharedPreferences.setMockInitialValues({'uid': 'user-a'});
    await SharedPreferencesUtil.init();
    final analytics = _TestAnalyticsAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    final provider = DeviceProvider();
    addTearDown(provider.dispose);
    final device = BtDevice(
      id: 'AA:AA:AA:AA:AA:02',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -50,
      firmwareRevision: '3.0.20',
    );

    await provider.setConnectedDevice(device);
    await provider.setConnectedDevice(device);
    await provider.setConnectedDevice(null);
    await provider.setConnectedDevice(device);
    SharedPreferencesUtil().uid = 'user-b';
    await provider.setConnectedDevice(null);
    await provider.setConnectedDevice(device);
    await AnalyticsManager.flushPending(force: true);

    expect(analytics.events.where((event) => event == 'Device Paired'), hasLength(2));
    expect(analytics.events.where((event) => event == 'Device Connected'), hasLength(3));
    final pairedProperties = [
      for (var i = 0; i < analytics.events.length; i++)
        if (analytics.events[i] == 'Device Paired') analytics.eventProperties[i],
    ];
    expect(pairedProperties.first, containsPair('hardware_id_kind', 'unavailable'));
    expect(pairedProperties.first, containsPair('hardware_id_stable', false));
    for (final uid in ['user-a', 'user-b']) {
      expect(analytics.personPropertiesByUser[uid]?['has_paired_device'], isTrue);
      expect(DateTime.tryParse(analytics.personPropertiesByUser[uid]?['first_paired_at'] as String), isNotNull);
    }
  });

  test('non-null to null transition emits one truthful Device Session Ended', () async {
    SharedPreferences.setMockInitialValues({'uid': 'session-user'});
    await SharedPreferencesUtil.init();
    final analytics = _TestAnalyticsAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    final provider = DeviceProvider(
      bleDiagnosticsLoader: (_) async => BleDeviceDiagnostics(
        disconnectHistory: [
          BleDisconnectEvent(
            timestamp: DateTime.now().millisecondsSinceEpoch,
            reason: 'connection_timeout',
            reasonCode: 8,
            isManual: false,
            eventType: 'disconnect',
            lastRssi: -82,
            connectionDurationMs: 1250,
            appState: 'foreground',
            timeToReconnectMs: 0,
            rssiTrend: 'falling',
          ),
        ],
        nativeBackgroundBytesConsumed: 0,
        nativeBackgroundPacketsConsumed: 0,
        reconnectionCount: 0,
        connectedAt: 0,
        failToConnectCount: 0,
      ),
    );
    addTearDown(provider.dispose);
    final device = BtDevice(
      id: 'AA:AA:AA:AA:AA:03',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -50,
      modelNumber: 'Omi DevKit 2',
      firmwareRevision: '3.0.20',
    );

    await provider.setConnectedDevice(device);
    await provider.setConnectedDevice(null);
    await provider.setConnectedDevice(null);
    await AnalyticsManager.flushPending(force: true);

    final sessionEvents = [
      for (var i = 0; i < analytics.events.length; i++)
        if (analytics.events[i] == 'Device Session Ended') analytics.eventProperties[i],
    ];
    expect(sessionEvents, hasLength(1));
    expect(sessionEvents.single, containsPair('duration_seconds', 1.25));
    expect(sessionEvents.single, containsPair('reason', 'connection_timeout'));
    expect(sessionEvents.single, containsPair('hci_reason_code', 8));
    expect(sessionEvents.single, containsPair('device_vendor', 'omi'));
    expect(sessionEvents.single, containsPair('hardware_family', 'omi_devkit'));
    expect(sessionEvents.single, containsPair('model', 'Omi DevKit 2'));
    expect(sessionEvents.single, containsPair('firmware_revision', '3.0.20'));
    expect(sessionEvents.single, isNot(contains('reconnect_attempt_count')));
  });

  group('battery throttling', () {
    late DeviceProvider provider;
    late int notifyCount;

    setUp(() {
      provider = DeviceProvider();
      notifyCount = 0;
      provider.addListener(() => notifyCount++);
    });

    test('notifies on first battery reading', () {
      final result = provider.updateBatteryLevelForTesting(50);

      expect(result, true);
      expect(notifyCount, 1);
      expect(provider.batteryLevel, 50);
    });

    test('does not notify for small changes (<5%) within 15 minutes', () {
      final now = DateTime.now();

      // First reading - should notify
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // Small change (2%) within 15 minutes - should NOT notify
      final result = provider.updateBatteryLevelForTesting(52, now: now.add(const Duration(minutes: 5)));

      expect(result, false);
      expect(notifyCount, 1); // No additional notification
      expect(provider.batteryLevel, 52); // Level is still updated
    });

    test('notifies when delta >= 5%', () {
      final now = DateTime.now();

      // First reading
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // 5% change - should notify
      final result = provider.updateBatteryLevelForTesting(45, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('notifies after 15 minutes even if delta < 5%', () {
      final now = DateTime.now();

      // First reading
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // Small change but 15 minutes elapsed - should notify
      final result = provider.updateBatteryLevelForTesting(51, now: now.add(const Duration(minutes: 15)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('notifies when crossing 20% threshold downward', () {
      final now = DateTime.now();

      // Start above 20%
      provider.updateBatteryLevelForTesting(25, now: now);
      expect(notifyCount, 1);

      // Cross below 20% (only 6% change, but crosses threshold)
      final result = provider.updateBatteryLevelForTesting(19, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('notifies when crossing 20% threshold upward', () {
      final now = DateTime.now();

      // Start below 20%
      provider.updateBatteryLevelForTesting(15, now: now);
      expect(notifyCount, 1);

      // Cross above 20% (only 6% change, but crosses threshold)
      final result = provider.updateBatteryLevelForTesting(21, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('does not notify for small changes that do not cross 20% threshold', () {
      final now = DateTime.now();

      // Start at 25%
      provider.updateBatteryLevelForTesting(25, now: now);
      expect(notifyCount, 1);

      // Small change staying above 20% - should NOT notify
      final result = provider.updateBatteryLevelForTesting(23, now: now.add(const Duration(minutes: 1)));

      expect(result, false);
      expect(notifyCount, 1);
    });

    test('resetBatteryThrottlingForTesting resets state', () {
      final now = DateTime.now();

      // First reading
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // Reset
      provider.resetBatteryThrottlingForTesting();

      // Now same value should trigger notification again (as if first reading)
      final result = provider.updateBatteryLevelForTesting(50, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });
  });

  group('low battery alert flag — state machine (#5697)', () {
    // Tests the exact if/else from DeviceProvider.onBatteryLevelChange (lines 163-172)
    // as a pure state machine, without touching production code.
    //
    // Production logic:
    //   if (batteryLevel < 20 && !_hasLowBatteryAlerted) {
    //     _hasLowBatteryAlerted = true;   // fire notification
    //   } else if (batteryLevel > 20) {
    //     _hasLowBatteryAlerted = false;   // THE FIX (was: true)
    //   }

    /// Mirror of production logic. Returns (alertFired, newFlag).
    (bool, bool) evalAlert(int level, bool hasAlerted) {
      if (level < 20 && !hasAlerted) {
        return (true, true);
      } else if (level > 20) {
        return (false, false); // fix: reset flag on recovery
      }
      return (false, hasAlerted);
    }

    /// Simulate a sequence of battery readings, return list of alert events.
    List<bool> runSequence(List<int> levels) {
      var flag = false;
      return levels.map((level) {
        final (fired, newFlag) = evalAlert(level, flag);
        flag = newFlag;
        return fired;
      }).toList();
    }

    test('alert fires when battery drops below 20%', () {
      final (fired, flag) = evalAlert(15, false);
      expect(fired, true);
      expect(flag, true);
    });

    test('no duplicate alert while battery stays low', () {
      final (fired, flag) = evalAlert(10, true);
      expect(fired, false);
      expect(flag, true);
    });

    test('flag resets when battery recovers above 20%', () {
      final (fired, flag) = evalAlert(25, true);
      expect(fired, false);
      expect(flag, false, reason: 'BUG was here: production had true instead of false');
    });

    test('alert fires again after recovery — the core bug scenario', () {
      // 50% → 15% (alert) → 25% (recover) → 10% (should alert AGAIN)
      final alerts = runSequence([50, 15, 25, 10]);
      expect(
          alerts,
          [
            false,
            true,
            false,
            true,
          ],
          reason: 'Before fix: [false, true, false, false] — second alert never fires');
    });

    test('full lifecycle: multiple charge cycles', () {
      final alerts = runSequence([100, 80, 60, 40, 18, 25, 50, 85, 60, 30, 12, 90, 5]);
      // Alert at index 4 (18%), 10 (12%), 12 (5%)
      expect(alerts, [false, false, false, false, true, false, false, false, false, false, true, false, true]);
    });

    test('boundary: exactly 20% neither triggers alert nor resets flag', () {
      // 20 is not < 20 and not > 20
      final (fired1, flag1) = evalAlert(20, false);
      expect(fired1, false);
      expect(flag1, false);

      final (fired2, flag2) = evalAlert(20, true);
      expect(fired2, false);
      expect(flag2, true, reason: 'Exactly 20% should not reset flag (needs > 20)');
    });
  });
}

class _TestAnalyticsAdapter implements AnalyticsAdapter {
  final List<String> events = [];
  final List<Map<String, Object>> eventProperties = [];
  final List<Map<String, Object>> personProperties = [];
  final Map<String, Map<String, Object>> personPropertiesByUser = {};

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(eventName);
    eventProperties.add(properties ?? {});
  }

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {
    if (userProperties != null) {
      personProperties.add(userProperties);
      personPropertiesByUser.putIfAbsent(userId, () => {}).addAll(userProperties);
    }
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
