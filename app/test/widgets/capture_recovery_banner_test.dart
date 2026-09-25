import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  List<({String event, Map<String, Object> properties})> events = [];

  CaptureWedgeMonitor makeMonitor({bool flagEnabled = true}) {
    return CaptureWedgeMonitor(
      featureGate: () async => flagEnabled,
      track: (event, properties) => events.add((event: event, properties: properties)),
      bleRetry: (_) async {},
      appBuild: () => '1',
      platform: () => 'ios',
    );
  }

  void zeroSession(CaptureWedgeMonitor monitor, {String source = 'omi'}) {
    final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: source);
    monitor.onCaptureSessionEnded(handle, binaryBytesSent: 0);
  }

  void wedge(CaptureWedgeMonitor monitor, {String source = 'omi'}) {
    zeroSession(monitor, source: source);
    zeroSession(monitor, source: source);
    zeroSession(monitor, source: source);
  }

  Future<void> pumpBanner(WidgetTester tester, CaptureWedgeMonitor monitor, {bool tickerEnabled = true}) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: TickerMode(enabled: tickerEnabled, child: CaptureRecoveryBanner(monitor: monitor))),
      ),
    );
    await tester.pump();
  }

  List<Map<String, Object>> forEvent(String name) =>
      events.where((e) => e.event == name).map((e) => e.properties).toList();

  setUp(() => events = []);

  group('CaptureRecoveryBanner', () {
    testWidgets('renders the repair prompt once the wedge is declared', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpBanner(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryBanner));
      expect(find.text(AppLocalizations.of(context).captureRecoveryBanner), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_banner')), findsOneWidget);
      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    testWidgets('prompt shown telemetry fires once even across rebuilds', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpBanner(tester, monitor);
      await pumpBanner(tester, monitor);
      await pumpBanner(tester, monitor);

      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    testWidgets('prompt shown waits for the banner to actually tick', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpBanner(tester, monitor, tickerEnabled: false);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);

      await pumpBanner(tester, monitor, tickerEnabled: true);
      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    testWidgets('tap opens /settings/device inside Home and sends actioned telemetry', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);
      final opened = <String>[];
      Future<void> opener(String route) async => opened.add(route);
      HomeNavigation.register(opener);
      addTearDown(() => HomeNavigation.unregister(opener));

      await pumpBanner(tester, monitor);
      await tester.tap(find.byKey(const Key('capture_recovery_banner')));
      await tester.pump();

      expect(opened, ['/settings/device']);
      expect(forEvent('Capture Recovery Actioned').single['surface'], 'banner');
    });

    testWidgets('disappears when a positive-byte session resolves the wedge', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);
      await pumpBanner(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_banner')), findsOneWidget);

      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: 64);
      await tester.pump();

      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
    });

    testWidgets('stays hidden for a phone capture source', (tester) async {
      final monitor = makeMonitor();
      zeroSession(monitor, source: 'phone');
      zeroSession(monitor, source: 'phone');
      zeroSession(monitor, source: 'phone');
      await pumpBanner(tester, monitor);

      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
      expect(forEvent('Capture Wedge Detected'), isEmpty);
    });

    testWidgets('stays hidden when the feature flag is off', (tester) async {
      final monitor = makeMonitor(flagEnabled: false);
      wedge(monitor);
      await pumpBanner(tester, monitor);

      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);
    });

    testWidgets('stays hidden when no wedge exists', (tester) async {
      final monitor = makeMonitor();
      await pumpBanner(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
    });
  });
}
