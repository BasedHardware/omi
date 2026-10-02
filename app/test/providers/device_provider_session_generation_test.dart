import 'dart:async';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
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

BtDevice _device() => BtDevice(
      id: 'AA:AA:AA:AA:AA:04',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -50,
      modelNumber: 'Omi DevKit 2',
      firmwareRevision: '3.0.20',
    );

BleDeviceDiagnostics _diagnostics() => BleDeviceDiagnostics(
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
    );

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

  test('clearUserData mid-disconnect refuses to publish Device Session Ended', () async {
    SharedPreferences.setMockInitialValues({'uid': 'session-user'});
    await SharedPreferencesUtil.init();
    final analytics = _TestAnalyticsAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();

    Completer<BleDeviceDiagnostics>? hang = Completer<BleDeviceDiagnostics>();
    final provider = DeviceProvider(
      bleDiagnosticsLoader: (_) {
        final pending = hang;
        if (pending != null) return pending.future;
        return Future.value(_diagnostics());
      },
    );
    addTearDown(provider.dispose);

    await provider.setConnectedDevice(_device());
    final disconnect = provider.setConnectedDevice(null);
    provider.clearUserData();
    expect(provider.isConnecting, isFalse);
    expect(provider.havingNewFirmware, isFalse);
    expect(provider.ringStatus, isNull);

    hang.complete(_diagnostics());
    hang = null;
    await disconnect;
    await AnalyticsManager.flushPending(force: true);

    expect(
      analytics.events.where((event) => event == 'Device Session Ended'),
      isEmpty,
      reason: 'finally must not recapture and publish the retired disconnect',
    );

    await provider.setConnectedDevice(_device());
    await provider.setConnectedDevice(null);
    await AnalyticsManager.flushPending(force: true);

    expect(
      analytics.events.where((event) => event == 'Device Session Ended'),
      hasLength(1),
      reason: 'a current-generation disconnect after clearUserData still publishes',
    );
  });

  test('clearUserData drops connecting and firmware publication', () {
    final provider = DeviceProvider();
    addTearDown(provider.dispose);
    provider.updateConnectingStatus(true);
    expect(provider.isConnecting, isTrue);

    provider.clearUserData();
    expect(provider.isConnecting, isFalse);
    expect(provider.havingNewFirmware, isFalse);
    expect(provider.ringStatus, isNull);
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
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
