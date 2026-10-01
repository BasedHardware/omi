import 'dart:convert';

import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _NoConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

BleDisconnectEvent _event(
  int timestamp, {
  String eventType = 'disconnect',
  int timeToReconnectMs = 0,
}) {
  return BleDisconnectEvent(
    timestamp: timestamp,
    reason: eventType == 'fail_to_connect' ? 'connection_timeout' : 'clean_disconnect',
    reasonCode: 8,
    isManual: false,
    eventType: eventType,
    lastRssi: -70,
    connectionDurationMs: eventType == 'disconnect' ? 60000 : 0,
    appState: 'background',
    timeToReconnectMs: timeToReconnectMs,
    rssiTrend: 'sudden',
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final mockedChannels = <String>{};

  void mockBleHostApi(String method, Object? reply) {
    final channel = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
    mockedChannels.add(channel);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      channel,
      (ByteData? message) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[reply]),
    );
  }

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _NoConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    mockBleHostApi('getBatteryHistory', <Object?>[]);
    mockBleHostApi('startRssiStreaming', null);
    mockBleHostApi('stopRssiStreaming', null);
  });

  tearDown(() {
    for (final channel in mockedChannels) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(channel, null);
    }
    mockedChannels.clear();
  });

  Future<void> pumpPage(WidgetTester tester) async {
    final provider = DeviceProvider();
    addTearDown(provider.dispose);
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: const DeviceDiagnostics(deviceId: 'AA:BB:CC:DD:EE:FF'),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('status cards lead with the 7-day window and keep lifetime as context', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final since = now - 3 * 24 * 3600 * 1000;
    mockBleHostApi(
      'getDeviceDiagnostics',
      BleDeviceDiagnostics(
        disconnectHistory: [
          _event(since - 24 * 3600 * 1000, timeToReconnectMs: 4000), // before the window anchor
          _event(since + 3600 * 1000, timeToReconnectMs: 5000), // recovered → counted
          _event(since + 90 * 60 * 1000, timeToReconnectMs: 6000), // recovered → counted
          _event(since + 2 * 3600 * 1000, eventType: 'fail_to_connect'), // counted as failed connect
          _event(since + 3 * 3600 * 1000, timeToReconnectMs: 0), // not yet reconnected → excluded
        ],
        reconnectionCount: 10048,
        connectedAt: now - 60000,
        failToConnectCount: 12,
        nativeBackgroundBytesConsumed: 0,
        nativeBackgroundPacketsConsumed: 0,
      ),
    );
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({'counters_since': since}));

    await pumpPage(tester);

    expect(find.text('Reconnections (last 7 days)'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('10048 since pairing'), findsOneWidget);
    expect(find.text('Failed connections (last 7 days)'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.text('12 since pairing'), findsOneWidget);
    // Lifetime numbers no longer hold the headline position.
    expect(find.text('10048'), findsNothing);
    expect(find.text('12'), findsNothing);
  });

  testWidgets('missing window anchor falls back to lifetime counts only', (tester) async {
    mockBleHostApi(
      'getDeviceDiagnostics',
      BleDeviceDiagnostics(
        disconnectHistory: const [],
        reconnectionCount: 10048,
        connectedAt: 0,
        failToConnectCount: 12,
        nativeBackgroundBytesConsumed: 0,
        nativeBackgroundPacketsConsumed: 0,
      ),
    );
    // No counters_since: extended diagnostics came back empty.
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({}));

    await pumpPage(tester);

    expect(find.text('Reconnections'), findsOneWidget);
    expect(find.text('10048'), findsOneWidget);
    expect(find.text('Failed connections'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.textContaining('since pairing'), findsNothing);
    expect(find.text('Reconnections (last 7 days)'), findsNothing);
    expect(find.text('Failed connections (last 7 days)'), findsNothing);
  });
}
