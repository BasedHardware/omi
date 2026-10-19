import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/capture_recovery_status.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
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

  Future<void> pumpStatus(WidgetTester tester, CaptureWedgeMonitor monitor, {bool tickerEnabled = true}) async {
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
            child: CaptureRecoveryStatus(monitor: monitor),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  List<Map<String, Object>> forEvent(String name) =>
      events.where((e) => e.event == name).map((e) => e.properties).toList();

  setUp(() => events = []);
  group('CaptureRecoveryStatus', () {
    testWidgets('renders reconnect action after a failed automatic BLE retry', (tester) async {
      final monitor = makeMonitor(bleRetry: (_) async => throw StateError('BLE unavailable'));
      wedge(monitor);

      await pumpStatus(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryStatus));
      expect(find.text(AppLocalizations.of(context).captureRecoveryBannerTitle), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_status')), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_status_retry')), findsOneWidget);
      expect(find.text(AppLocalizations.of(context).reconnect), findsOneWidget);
      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    testWidgets('prompt shown telemetry fires once even across rebuilds', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpStatus(tester, monitor);
      await pumpStatus(tester, monitor);
      await pumpStatus(tester, monitor);

      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    testWidgets('prompt shown waits for the banner to actually tick', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpStatus(tester, monitor, tickerEnabled: false);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);

      await pumpStatus(tester, monitor, tickerEnabled: true);
      expect(forEvent('Capture Recovery Prompt Shown'), hasLength(1));
    });

    testWidgets('Reconnect retries in place and never opens a settings route', (tester) async {
      var bleRetries = 0;
      // The automatic retry at declaration completes at once; the reader's retry is held in
      // flight, so the test can see the line step aside while it runs.
      final held = Completer<void>();
      final monitor = makeMonitor(bleRetry: (_) {
        bleRetries++;
        return bleRetries == 1 ? Future.value() : held.future;
      });
      wedge(monitor);
      final opened = <String>[];
      Future<bool> opener(String route, {bool Function()? canOpen}) async {
        opened.add(route);
        return true;
      }

      HomeNavigation.register(opener);
      addTearDown(() => HomeNavigation.unregister(opener));

      await pumpStatus(tester, monitor);
      final retriesBeforeTap = bleRetries;
      expect(retriesBeforeTap, 1, reason: 'declaration already attempted one automatic retry');

      await tester.tap(find.byKey(const Key('capture_recovery_status_retry')));
      await tester.pump();

      expect(bleRetries, retriesBeforeTap + 1, reason: 'Reconnect retries the same episode in place, once');
      expect(opened, isEmpty, reason: 'a stalled BLE link is fixed where the reader stands, not in settings');
      expect(forEvent('Capture Recovery Actioned').single['surface'], 'live_status');
      expect(find.byKey(const Key('capture_recovery_status')), findsNothing,
          reason: 'the line leaves while the retry runs');

      held.complete();
      await tester.pump();
      expect(find.byKey(const Key('capture_recovery_status')), findsOneWidget,
          reason: 'a retry that brought no audio back puts the line back');
    });

    testWidgets('tapping the message opens the details sheet with the BLE explanation', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpStatus(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryStatus));
      final l10n = AppLocalizations.of(context);

      await tester.tap(find.byKey(const Key('capture_recovery_status_details')));
      await tester.pumpAndSettle();

      expect(find.text(l10n.captureRecoveryBannerTitle), findsNWidgets(2),
          reason: 'the line and the sheet title both name the episode');
      expect(find.text(l10n.captureWedgeBleExplanation), findsOneWidget);

      await tester.tap(find.text(l10n.gotIt));
      await tester.pumpAndSettle();
      expect(find.text(l10n.captureWedgeBleExplanation), findsNothing);
    });

    testWidgets('has no dismiss control: the line clears itself when audio returns', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpStatus(tester, monitor);

      expect(find.byKey(const Key('capture_recovery_status')), findsOneWidget);
      expect(find.byIcon(Icons.close), findsNothing);
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
      await pumpStatus(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryStatus));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.captureIngressNeedsReconnect), findsOneWidget,
          reason: 'the title names the required manual action, not a wait or a retry');
      expect(find.text(l10n.captureRecoveryBannerTitle), findsNothing,
          reason: 'the stall title would promise a reconnect this trigger cannot perform');
      expect(find.text(l10n.captureAudioSavedTranscribesLater), findsNothing,
          reason: 'an ingress failure proves ingress, not durability (INV-CAP-1)');
      expect(find.byKey(const Key('capture_recovery_status_retry')), findsNothing,
          reason: 'no retry affordance when the Dart-side retry would no-op');
    });

    testWidgets('every action on the line keeps a 44-point target', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);

      await pumpStatus(tester, monitor);

      for (final key in const [
        Key('capture_recovery_status_retry'),
        Key('capture_recovery_status_details'),
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

      await pumpStatus(tester, monitor);
      final retriesBeforeTap = retries;
      final context = tester.element(find.byType(CaptureRecoveryStatus));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.captureBannerRetrySync), findsOneWidget,
          reason: 'the storage primary action names what its retry does');
      expect(find.text(l10n.reconnect), findsNothing);

      await tester.tap(find.byKey(const Key('capture_recovery_status_retry')));
      await tester.pump();

      expect(retries, retriesBeforeTap + 1, reason: 'storage keeps its transfer-recovery tap');
      expect(find.text(AppLocalizations.of(context).captureAudioSavedTranscribesLater), findsNothing,
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

      await pumpStatus(tester, monitor);
      expect(retries, 1, reason: 'declaration attempts one automatic recovery');
      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
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

      await pumpStatus(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
      expect(retries, 1);
      expect(forEvent('Capture Wedge Detected').single['trigger'], CaptureWedgeMonitor.triggerBytesSentNoTranscript);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);
      monitor.dispose();
    });

    testWidgets('admission-blocked storage shows a localized phone-storage risk warning', (tester) async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');

      await pumpStatus(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryStatus));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.capturePhoneStorageFull), findsOneWidget);
      expect(find.byKey(const Key('capture_recovery_status')), findsOneWidget);
    });

    testWidgets('a storage episode whose probe failed does not claim the disk is full', (tester) async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_space_unknown');

      await pumpStatus(tester, monitor);

      final context = tester.element(find.byType(CaptureRecoveryStatus));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.activityAttentionStorageUnknownTitle), findsOneWidget);
      expect(find.text(l10n.capturePhoneStorageFull), findsNothing);
    });

    testWidgets('disappears when a positive-byte session resolves the wedge', (tester) async {
      final monitor = makeMonitor();
      wedge(monitor);
      await pumpStatus(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_status')), findsOneWidget);

      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onTranscriptObserved('dev-a');
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: 64);
      await tester.pump();

      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
      expect(forEvent('Capture Recovery Resolved'), hasLength(1));
    });

    test('an acute link episode re-labels the header; a storage episode does not', () async {
      final acute = makeMonitor();
      wedge(acute);
      await pumpEventQueue();
      expect(CaptureRecoveryStatus.overridesHeader(acute), isTrue,
          reason: 'audio is not reaching the app: the header reads Reconnecting');

      final storage = makeMonitor();
      storage.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');
      expect(CaptureRecoveryStatus.overridesHeader(storage), isFalse,
          reason: 'recording continues on the device; the header stays live');
      acute.dispose();
      storage.dispose();
    });

    testWidgets('a pendant stall outranks an open storage episode, and Reconnect retries the link', (tester) async {
      var bleRetries = 0;
      var transferRetries = 0;
      final monitor = makeMonitor(bleRetry: (_) async => bleRetries++, transferRetry: () async => transferRetries++);
      monitor.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');
      wedge(monitor);

      await pumpStatus(tester, monitor);
      final context = tester.element(find.byType(CaptureRecoveryStatus));
      expect(find.text(AppLocalizations.of(context).captureRecoveryBannerTitle), findsOneWidget);
      final ble = bleRetries;
      final transfer = transferRetries;

      await tester.tap(find.byKey(const Key('capture_recovery_status_retry')));
      await tester.pump();
      expect(bleRetries, ble + 1, reason: 'Reconnect retries the stalled link');
      expect(transferRetries, transfer, reason: 'not the storage transfer behind it');
    });

    testWidgets('the header reads Reconnecting for a stall, including while the retry runs', (tester) async {
      var bleRetries = 0;
      final held = Completer<void>();
      final monitor = makeMonitor(bleRetry: (_) {
        bleRetries++;
        return bleRetries == 1 ? Future.value() : held.future;
      });
      wedge(monitor);
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          appBar: CaptureWedgeAppBar(
            monitor: monitor,
            // A pendant whose capture is not yet verified: the stall must still force the status.
            showStatus: false,
            state: CaptureDisplayState.listening,
            sourceLabel: 'Pendant',
          ),
          body: CaptureRecoveryStatus(monitor: monitor),
        ),
      ));
      await tester.pump();
      final l10n = AppLocalizations.of(tester.element(find.byType(CaptureRecoveryStatus)));
      final reconnecting = l10n.captureStatusWithSource(l10n.reconnecting, 'Pendant');
      expect(find.text(reconnecting), findsOneWidget);

      await tester.tap(find.byKey(const Key('capture_recovery_status_retry')));
      await tester.pump();
      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
      expect(find.text(reconnecting), findsOneWidget,
          reason: 'no live label while the retry runs and no audio reaches the app');

      held.complete();
      await tester.pump();
      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onTranscriptObserved('dev-a');
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: 64);
      await tester.pump();
      expect(find.text(reconnecting), findsNothing, reason: 'audio flows again: the header is live');
    });

    testWidgets('a storage episode leaves the header live', (tester) async {
      final monitor = makeMonitor(transferRetry: () async {});
      monitor.observeStorageAtRisk(
          engagedAt: DateTime(2026), blockedCount: 1, retainedCount: 720, reason: 'disk_reserve');
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          appBar: CaptureWedgeAppBar(
              monitor: monitor, showStatus: true, state: CaptureDisplayState.listening, sourceLabel: 'Pendant'),
        ),
      ));
      await tester.pump();
      final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
      expect(find.text(l10n.captureStatusWithSource(l10n.listening, 'Pendant')), findsOneWidget);
    });

    testWidgets('stays hidden for a phone capture source', (tester) async {
      final monitor = makeMonitor();
      zeroSession(monitor, source: 'phone');
      zeroSession(monitor, source: 'phone');
      zeroSession(monitor, source: 'phone');
      await pumpStatus(tester, monitor);

      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
      expect(forEvent('Capture Wedge Detected'), isEmpty);
    });

    testWidgets('stays hidden when the feature flag is off', (tester) async {
      final monitor = makeMonitor(flagEnabled: false);
      wedge(monitor);
      await pumpStatus(tester, monitor);

      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
      expect(forEvent('Capture Recovery Prompt Shown'), isEmpty);
    });

    testWidgets('stays hidden when no wedge exists', (tester) async {
      final monitor = makeMonitor();
      await pumpStatus(tester, monitor);
      expect(find.byKey(const Key('capture_recovery_status')), findsNothing);
    });
  });
}
