import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/capture_recovery_banner.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/capture/capture_ingress_health.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  List<({String event, Map<String, Object> properties})> events = [];

  CaptureWedgeMonitor makeMonitor({
    bool flagEnabled = true,
    DateTime Function()? now,
    Future<void> Function()? transferRetry,
    Future<void> Function(String deviceId)? bleRetry,
  }) {
    return CaptureWedgeMonitor(
      now: now,
      featureGate: () async => flagEnabled,
      track: (event, properties) => events.add((event: event, properties: properties)),
      bleRetry: bleRetry ?? (_) async {},
      transferRetry: transferRetry,
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
        home: Scaffold(
          body: TickerMode(
            enabled: tickerEnabled,
            child: CaptureRecoveryBanner(monitor: monitor),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  List<Map<String, Object>> forEvent(String name) =>
      events.where((e) => e.event == name).map((e) => e.properties).toList();

  setUp(() => events = []);
  group('CaptureRecoveryBanner', () {
    testWidgets('renders reconnect action after a failed automatic BLE retry', (tester) async {
      final monitor = makeMonitor(bleRetry: (_) async => throw StateError('BLE unavailable'));
      wedge(monitor);

      await pumpBanner(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryBanner));
      expect(find.text(AppLocalizations.of(context).captureRecoveryBanner), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_banner')), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_banner_retry')), findsOneWidget);
      expect(find.text(AppLocalizations.of(context).captureBannerTryReconnect), findsOneWidget);
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

    testWidgets('tap retries in place and never opens a settings route', (tester) async {
      var bleRetries = 0;
      final monitor = makeMonitor(bleRetry: (_) async => bleRetries++);
      wedge(monitor);
      final opened = <String>[];
      Future<bool> opener(String route, {bool Function()? canOpen}) async {
        opened.add(route);
        return true;
      }

      HomeNavigation.register(opener);
      addTearDown(() => HomeNavigation.unregister(opener));

      await pumpBanner(tester, monitor);
      final retriesBeforeTap = bleRetries;
      expect(retriesBeforeTap, 1, reason: 'declaration already attempted one automatic retry');

      // Tap the card body (the title area), not a control inside it.
      final card = find.byKey(const Key('capture_recovery_banner'));
      await tester.tapAt(tester.getTopLeft(card) + const Offset(60, 10));
      await tester.pump();

      expect(bleRetries, retriesBeforeTap + 1, reason: 'the banner tap retries the same episode in place');
      expect(opened, isEmpty, reason: 'a stalled BLE link is fixed where the reader stands, not in settings');
      expect(forEvent('Capture Recovery Actioned').single['surface'], 'banner');
      expect(find.byIcon(Icons.chevron_right), findsNothing);
    });

    testWidgets('the Try reconnect button retries once, without the card gesture double-firing', (tester) async {
      var bleRetries = 0;
      final monitor = makeMonitor(bleRetry: (_) async => bleRetries++);
      wedge(monitor);

      await pumpBanner(tester, monitor);
      final retriesBeforeTap = bleRetries;

      await tester.tap(find.byKey(const Key('capture_recovery_banner_retry')));
      await tester.pump();

      expect(bleRetries, retriesBeforeTap + 1,
          reason: 'the button runs the same recovery as the card tap, and only once');
      expect(forEvent('Capture Recovery Actioned'), hasLength(1));
    });

    testWidgets('What\'s going on? opens the details sheet with the BLE explanation', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpBanner(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryBanner));
      final l10n = AppLocalizations.of(context);

      await tester.tap(find.byKey(const Key('capture_recovery_banner_info')));
      await tester.pumpAndSettle();

      expect(find.text(l10n.captureRecoveryBanner), findsNWidgets(2),
          reason: 'the banner and the sheet title both name the episode');
      expect(find.text(l10n.captureWedgeBleExplanation), findsOneWidget);

      await tester.tap(find.text(l10n.gotIt));
      await tester.pumpAndSettle();
      expect(find.text(l10n.captureWedgeBleExplanation), findsNothing);
    });

    testWidgets('the dismiss control hides the episode through the monitor', (tester) async {
      final monitor = _DismissRecordingMonitor();
      wedge(monitor);

      await pumpBanner(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_banner')), findsOneWidget);

      await tester.tap(find.byKey(const Key('capture_recovery_banner_dismiss')));
      await tester.pump();

      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
      expect(monitor.dismissedDeviceIds, ['dev-a']);
    });

    testWidgets('an exhausted native ingress recovery informs, never offers a dead-end retry', (tester) async {
      final monitor = makeMonitor(bleRetry: (_) async {});
      monitor.observeIngressHealth(
        'dev-a',
        const CaptureIngressHealth(
          phase: 'actionRequired',
          generation: 'g1',
          reason: 'subscription_timeout',
          validUntilMs: 0,
          subscriptionConfirmed: false,
          unverifiedSinceMs: 60000,
        ),
      );
      await pumpBanner(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryBanner));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.captureIngressNeedsReconnect), findsOneWidget,
          reason: 'the title names the required manual action, not a wait or a retry');
      expect(find.text(l10n.captureRecoveryBanner), findsNothing,
          reason: '"tap to reconnect" would promise an action this trigger cannot perform');
      expect(find.text(l10n.captureAudioSavedTranscribesLater), findsNothing,
          reason: 'an ingress failure proves ingress, not durability (INV-CAP-1)');
      expect(find.byKey(const Key('capture_recovery_banner_retry')), findsNothing,
          reason: 'no retry affordance when the Dart-side retry would no-op');
    });

    testWidgets('every banner action keeps a 44-point target', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpBanner(tester, monitor);

      for (final key in const [
        Key('capture_recovery_banner_retry'),
        Key('capture_recovery_banner_info'),
        Key('capture_recovery_banner_dismiss'),
      ]) {
        final size = tester.getSize(find.byKey(key));
        expect(size.height, greaterThanOrEqualTo(44), reason: 'UX contract: 44pt minimum tap target');
      }
    });

    testWidgets('the storage episode taps through to a transfer retry, with no audio-safe detail line', (tester) async {
      var retries = 0;
      final monitor = makeMonitor(transferRetry: () async => retries++);
      monitor.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');

      await pumpBanner(tester, monitor);
      final retriesBeforeTap = retries;
      final context = tester.element(find.byType(CaptureRecoveryBanner));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.captureBannerRetrySync), findsOneWidget,
          reason: 'the storage primary action names what its retry does');
      expect(find.text(l10n.captureBannerTryReconnect), findsNothing);

      await tester.tap(find.byKey(const Key('capture_recovery_banner_retry')));
      await tester.pump();

      expect(retries, retriesBeforeTap + 1, reason: 'storage keeps its transfer-recovery tap');
      expect(find.text(AppLocalizations.of(context).captureAudioSavedTranscribesLater), findsNothing,
          reason: 'the storage title already says what is unsynced');
      expect(find.text(AppLocalizations.of(context).captureLinkStalledTranscribesLater), findsNothing,
          reason: 'the storage title already says what is unsynced');
    });

    testWidgets('stale upload backlog retries transfer without a duplicate banner', (tester) async {
      var retries = 0;
      final monitor = makeMonitor(
        flagEnabled: false,
        transferRetry: () async {
          retries++;
        },
      );
      monitor.observeWalBacklog(pendingCount: 2, oldestPendingAt: DateTime.now().subtract(const Duration(hours: 3)));

      await pumpBanner(tester, monitor);
      expect(retries, 1, reason: 'declaration attempts one automatic recovery');
      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
      expect(forEvent('Capture Wedge Detected').single['trigger'], CaptureWedgeMonitor.triggerUploadSilence);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);
    });

    testWidgets('two minutes of byte-producing silence has no banner', (tester) async {
      var now = DateTime(2026, 9, 28);
      var retries = 0;
      final monitor = makeMonitor(now: () => now, transferRetry: () async => retries++);
      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onSocketBytesSent(handle, 640);
      now = now.add(const Duration(minutes: 2));
      monitor.runConnectedWatchdog();

      await pumpBanner(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_banner')), findsNothing);
      expect(retries, 1);
      expect(forEvent('Capture Wedge Detected').single['trigger'], CaptureWedgeMonitor.triggerBytesSentNoTranscript);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);
      monitor.dispose();
    });

    testWidgets('admission-blocked storage shows a localized phone-storage risk warning', (tester) async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');

      await pumpBanner(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryBanner));
      final l10n = AppLocalizations.of(context);
      expect(find.text('${l10n.phoneStorage}: ${l10n.recordingsNotSynced}'), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_banner')), findsOneWidget);
    });

    testWidgets('disappears when a positive-byte session resolves the wedge', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);
      await pumpBanner(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_banner')), findsOneWidget);

      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onTranscriptObserved('dev-a');
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

/// Records the dismiss calls the banner makes, so a test can assert the monitor
/// received them without trusting the banner's disappearance alone.
class _DismissRecordingMonitor extends CaptureWedgeMonitor {
  _DismissRecordingMonitor()
      : super(
          featureGate: () async => true,
          track: (event, properties) {},
          bleRetry: (_) async {},
          appBuild: () => '1',
          platform: () => 'ios',
        );

  final List<String> dismissedDeviceIds = [];

  @override
  void dismissVisibleEpisode(String deviceId) {
    dismissedDeviceIds.add(deviceId);
    super.dismissVisibleEpisode(deviceId);
  }
}
