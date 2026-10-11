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
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _NoConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

BleDisconnectEvent _event(int timestamp, {String eventType = 'disconnect', int timeToReconnectMs = 0}) {
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

  BleDeviceDiagnostics diagnostics(
    List<BleDisconnectEvent> history, {
    int reconnectionCount = 10048,
    int failToConnectCount = 12,
    int? connectedAt,
  }) {
    return BleDeviceDiagnostics(
      disconnectHistory: history,
      reconnectionCount: reconnectionCount,
      connectedAt: connectedAt ?? DateTime.now().millisecondsSinceEpoch - 60000,
      failToConnectCount: failToConnectCount,
      nativeBackgroundBytesConsumed: 0,
      nativeBackgroundPacketsConsumed: 0,
    );
  }

  Color? textColor(WidgetTester tester, String text) => tester.widget<Text>(find.text(text)).style?.color;

  testWidgets('Last 7 Days leads with the window counts and keeps lifetime in the footnote', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final since = now - 3 * 24 * 3600 * 1000;
    mockBleHostApi(
      'getDeviceDiagnostics',
      diagnostics([
        _event(since - 24 * 3600 * 1000, timeToReconnectMs: 4000), // before the window anchor
        _event(since + 3600 * 1000, timeToReconnectMs: 5000), // recovered → counted
        _event(since + 90 * 60 * 1000, timeToReconnectMs: 7000), // recovered → counted
        _event(since + 2 * 3600 * 1000, eventType: 'fail_to_connect'), // counted as failed connect
        _event(since + 3 * 3600 * 1000, timeToReconnectMs: 0), // not yet reconnected → excluded
      ]),
    );
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({'counters_since': since}));

    await pumpPage(tester);

    expect(find.text('Right Now'), findsOneWidget);
    expect(find.text('Last 7 Days'), findsOneWidget);
    expect(find.text('Drops'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    expect(find.text('Failed connections'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.text('Longest gap'), findsOneWidget);
    expect(find.text('7s'), findsOneWidget);
    expect(find.text('Since pairing: 10048 drops, 12 failed connections.'), findsOneWidget);
    // The failed connect is days old, so the verdict stays healthy; median of 5 s and 7 s.
    expect(find.byKey(const Key('diagnostics_verdict_ok')), findsOneWidget);
    expect(find.text('Brief drops, back in about 6s each time'), findsOneWidget);
    // Counts are neutral text, never status colours.
    expect(textColor(tester, '2'), OmiColors.textSecondary);
    expect(textColor(tester, '1'), OmiColors.textSecondary);
    // Lifetime numbers no longer hold the headline position.
    expect(find.text('10048'), findsNothing);
    expect(find.text('12'), findsNothing);
  });

  for (final hasRecentEvents in [false, true]) {
    testWidgets('seven-day cards expire retained events without another native write ($hasRecentEvents)', (
      tester,
    ) async {
      final now = DateTime.now().millisecondsSinceEpoch;
      const dayMs = 24 * 3600 * 1000;
      mockBleHostApi(
        'getDeviceDiagnostics',
        BleDeviceDiagnostics(
          disconnectHistory: [
            _event(now - 8 * dayMs, timeToReconnectMs: 5000),
            _event(now - 8 * dayMs, eventType: 'fail_to_connect'),
            if (hasRecentEvents) _event(now - dayMs, timeToReconnectMs: 6000),
            if (hasRecentEvents) _event(now - dayMs, eventType: 'fail_to_connect'),
          ],
          reconnectionCount: 10048,
          connectedAt: 0,
          failToConnectCount: 12,
          nativeBackgroundBytesConsumed: 0,
          nativeBackgroundPacketsConsumed: 0,
        ),
      );
      mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({'counters_since': now - 14 * dayMs}));

      await pumpPage(tester);

      expect(find.text('Drops'), findsOneWidget);
      expect(find.text('Failed connections'), findsOneWidget);
      expect(find.text(hasRecentEvents ? '1' : '0'), findsNWidgets(2));
      expect(find.text('Since pairing: 10048 drops, 12 failed connections.'), findsOneWidget);
    });
  }

  testWidgets('missing window anchor falls back to lifetime counts, labelled since pairing', (tester) async {
    mockBleHostApi('getDeviceDiagnostics', diagnostics(const [], connectedAt: 0));
    // No counters_since: extended diagnostics came back empty.
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({}));

    await pumpPage(tester);

    expect(find.text('Drops'), findsOneWidget);
    expect(find.text('10048 since pairing'), findsOneWidget);
    expect(find.text('Failed connections'), findsOneWidget);
    expect(find.text('12 since pairing'), findsOneWidget);
    expect(find.textContaining('Since pairing:'), findsNothing);
    expect(find.text('No drops this week'), findsOneWidget);
  });

  testWidgets('a failed connection in the last 24 hours turns the verdict', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    mockBleHostApi(
      'getDeviceDiagnostics',
      diagnostics([
        _event(now - 5 * 3600 * 1000, timeToReconnectMs: 2000),
        _event(now - 2 * 3600 * 1000, eventType: 'fail_to_connect'),
      ], failToConnectCount: 1),
    );
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({'counters_since': now - 30 * 24 * 3600 * 1000}));

    await pumpPage(tester);

    expect(find.byKey(const Key('diagnostics_verdict_trouble')), findsOneWidget);
    expect(find.text('Having trouble connecting'), findsOneWidget);
    expect(find.text('Failed connections in the last 24 hours: 1'), findsOneWidget);
    expect(find.byKey(const Key('diagnostics_verdict_ok')), findsNothing);
  });

  testWidgets('history dots: red only for a failed connection in the last 24 hours', (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    const hour = 3600 * 1000;
    mockBleHostApi(
      'getDeviceDiagnostics',
      diagnostics([
        _event(now - 48 * hour), // no recorded reconnect time: still routine
        _event(now - 30 * hour, eventType: 'fail_to_connect'),
        _event(now - 2 * hour, eventType: 'fail_to_connect'),
      ], failToConnectCount: 2),
    );
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({'counters_since': now - 30 * 24 * hour}));

    await pumpPage(tester);

    List<Color?> dots() => tester
        .widgetList<Container>(find.byType(Container))
        .map((c) => c.decoration)
        .whereType<BoxDecoration>()
        .where((d) => d.shape == BoxShape.circle)
        .map((d) => d.color)
        .toList();
    expect(dots().where((c) => c == OmiColors.danger), hasLength(1));
    expect(dots().where((c) => c == OmiColors.warning), hasLength(1));
    expect(dots().where((c) => c == OmiColors.textTertiary), hasLength(1));
  });

  testWidgets("David's week renders healthy: 357 recovered drops, one long gap, no failures", (tester) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    const week = 7 * 24 * 3600 * 1000;
    mockBleHostApi(
      'getDeviceDiagnostics',
      diagnostics(
        [
          for (var i = 0; i < 357; i++)
            _event(now - week + (i + 1) * week ~/ 358, timeToReconnectMs: i == 100 ? 40000 : 1000 + (i % 3) * 1000),
        ],
        reconnectionCount: 368,
        failToConnectCount: 0,
      ),
    );
    mockBleHostApi('getExtendedDeviceDiagnostics', jsonEncode({'counters_since': now - 30 * 24 * 3600 * 1000}));

    await pumpPage(tester);
    BleBridge.instance.onRssiUpdate('AA:BB:CC:DD:EE:FF', -68);
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Reconnects on its own'), findsOneWidget);
    expect(find.text('Brief drops, back in about 2s each time'), findsOneWidget);
    expect(find.text('357'), findsOneWidget);
    expect(find.text('about 2 an hour'), findsOneWidget);
    expect(find.text('40s'), findsOneWidget);
    expect(find.text('Since pairing: 368 drops, 0 failed connections.'), findsOneWidget);
    expect(textColor(tester, '357'), OmiColors.textSecondary);
    // −68 dBm is Good, and Good is green.
    expect(find.text('Good'), findsOneWidget);
    expect(find.text('-68 dBm'), findsOneWidget);
  });

  group('thresholds', () {
    test('signal word and colour share one set of bands', () {
      expect(diagnosticsSignalFor(-55), DiagnosticsSignal.excellent);
      expect(diagnosticsSignalFor(-60), DiagnosticsSignal.excellent);
      expect(diagnosticsSignalFor(-68), DiagnosticsSignal.good);
      expect(diagnosticsSignalFor(-75), DiagnosticsSignal.good);
      expect(diagnosticsSignalFor(-76), DiagnosticsSignal.fair);
      expect(diagnosticsSignalFor(-85), DiagnosticsSignal.fair);
      expect(diagnosticsSignalFor(-86), DiagnosticsSignal.weak);
      expect(diagnosticsSignalColor(-60), OmiColors.success);
      expect(diagnosticsSignalColor(-68), OmiColors.success);
      expect(diagnosticsSignalColor(-75), OmiColors.success);
      expect(diagnosticsSignalColor(-76), OmiColors.warning);
      expect(diagnosticsSignalColor(-85), OmiColors.warning);
      expect(diagnosticsSignalColor(-86), OmiColors.danger);
    });

    test('battery is green above 20%, amber to 11%, red at 10% and below', () {
      expect(diagnosticsBatteryColor(100), OmiColors.success);
      expect(diagnosticsBatteryColor(21), OmiColors.success);
      expect(diagnosticsBatteryColor(20), OmiColors.warning);
      expect(diagnosticsBatteryColor(11), OmiColors.warning);
      expect(diagnosticsBatteryColor(10), OmiColors.danger);
      expect(diagnosticsBatteryColor(0), OmiColors.danger);
    });
  });

  group('summarizeDiagnostics', () {
    const hour = 3600 * 1000;
    final now = DateTime(2026, 10, 3, 12).millisecondsSinceEpoch;

    test('long gaps never turn the verdict; only a failed connect in 24 h does', () {
      final gaps = summarizeDiagnostics(
        [
          _event(now - 2 * hour, timeToReconnectMs: 45 * 60 * 1000),
          _event(now - 30 * hour, eventType: 'fail_to_connect'),
        ],
        nowMs: now,
        sinceMs: now - 48 * hour,
      );
      expect(gaps.hasTrouble, isFalse);
      expect(gaps.longestGapMs, 45 * 60 * 1000);
      expect(gaps.failed, 1);
      expect(gaps.failedLast24h, 0);

      final recent = summarizeDiagnostics(
        [_event(now - 23 * hour, eventType: 'fail_to_connect')],
        nowMs: now,
        sinceMs: now - 48 * hour,
      );
      expect(recent.hasTrouble, isTrue);
      expect(recent.failedLast24h, 1);
    });

    test('median, longest gap and hourly rate over the window', () {
      final summary = summarizeDiagnostics(
        [
          _event(now - 200 * hour, timeToReconnectMs: 99000), // before the anchor
          _event(now - 3 * hour, timeToReconnectMs: 1000),
          _event(now - 2 * hour, timeToReconnectMs: 3000),
          _event(now - 1 * hour, timeToReconnectMs: 2000),
          _event(now - 1 * hour, timeToReconnectMs: 0), // not reconnected
        ],
        nowMs: now,
        sinceMs: now - 2 * hour,
      );
      expect(summary.drops, 2);
      expect(summary.medianReconnectMs, 2500);
      expect(summary.longestGapMs, 3000);
      expect(summary.dropsPerHour, 1);
    });

    test('no drops and no window anchor leave the derived values empty', () {
      final summary = summarizeDiagnostics(const [], nowMs: now);
      expect(summary.drops, 0);
      expect(summary.medianReconnectMs, isNull);
      expect(summary.longestGapMs, isNull);
      expect(summary.dropsPerHour, isNull);
      expect(summary.hasTrouble, isFalse);
    });
  });
}
