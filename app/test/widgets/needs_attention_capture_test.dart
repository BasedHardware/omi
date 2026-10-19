import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/activity/activity_bell_button.dart';
import 'package:omi/pages/activity/activity_page.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/activity/needs_attention_section.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/capture/capture_ingress_health.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';

/// Capture problems (a stalled pendant link, a full phone disk, a stalled upload) live in
/// Activity's Needs attention section and light the bell's warning dot, never a banner on Home.

class _IdleSync extends ChangeNotifier implements SyncProvider {
  @override
  List<Wal> get allWals => const [];
  @override
  List<Wal> get displaySortedWals => const [];
  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isRateLimited => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<PendingWorkStore> _noWork() async {
  final store = PendingWorkStore(
    loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
    loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
  );
  await store.refresh();
  return store;
}

/// The section only reads the store; empty attention needs no refresh.
PendingWorkStore _emptyStore() => PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );

CaptureWedgeMonitor _monitor() => CaptureWedgeMonitor(
      featureGate: () async => true,
      track: (_, __) {},
      bleRetry: (_) async {},
      transferRetry: () async {},
      appBuild: () => '1',
      platform: () => 'ios',
    );

void _seedStorage(CaptureWedgeMonitor monitor, {int blockedCount = 3}) => monitor.observeStorageAtRisk(
      engagedAt: DateTime.now().subtract(const Duration(minutes: 30)),
      blockedCount: blockedCount,
      retainedCount: 720,
      reason: 'disk_reserve',
    );

void _seedUploadStall(CaptureWedgeMonitor monitor, {int pendingCount = 5, int pendingSeconds = 47 * 60}) =>
    monitor.observeWalBacklog(
      pendingCount: pendingCount,
      oldestPendingAt: DateTime.now().subtract(const Duration(hours: 3)),
      pendingSeconds: pendingSeconds,
    );

ConversationProvider _conversations() => ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );

Widget _app(Widget child, {CaptureWedgeMonitor? monitor, NavigatorObserver? observer}) => MultiProvider(
      providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: _IdleSync()),
        ChangeNotifierProvider<ConversationProvider>.value(value: _conversations()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        navigatorObservers: observer == null ? const [] : [observer],
        home: Scaffold(
          body: SingleChildScrollView(
            child: NeedsAttentionSection(store: _emptyStore(), captureMonitor: monitor),
          ),
        ),
      ),
    );

/// Counts pushes so a tap can be proven to open exactly one page without depending on the
/// destination page's own provider needs.
class _PushCounter extends NavigatorObserver {
  int count = 0;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    count++;
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  final yesterday = DateTime.now().subtract(const Duration(days: 1));

  Widget pageApp(Widget home) => MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: home,
      );

  group('NeedsAttentionSection capture rows', () {
    testWidgets('storage at risk renders its row without an attempt count', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedStorage(monitor, blockedCount: 3);

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.byKey(const Key('activity_attention_storage')), findsOneWidget);
      // blockedCount counts admission attempts, not recordings, so the row never
      // renders it as a count of paused recordings.
      expect(find.text('Phone storage full'), findsOneWidget);
      expect(find.textContaining('3'), findsNothing);
      expect(find.text('Recordings paused'), findsOneWidget);
      expect(find.byType(OmiButton), findsNothing, reason: 'a settings-style row: no button');
      expect(find.byIcon(Icons.chevron_right), findsOneWidget, reason: 'the row opens Offline Sync');
      expect(find.byKey(const Key('activity_attention_upload_stalled')), findsNothing);
    });

    testWidgets('an upload stall renders its row with the kept-audio length', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedUploadStall(monitor, pendingCount: 5, pendingSeconds: 47 * 60);

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.byKey(const Key('activity_attention_upload_stalled')), findsOneWidget);
      expect(find.text('Upload stalled'), findsOneWidget);
      expect(find.text('5 recordings waiting · 47m'), findsOneWidget);
      expect(find.byType(OmiButton), findsNothing, reason: 'a settings-style row: no button');
      expect(find.byIcon(Icons.chevron_right), findsOneWidget, reason: 'the row opens Offline Sync');
      expect(find.byKey(const Key('activity_attention_storage')), findsNothing);
    });

    testWidgets('a storage row whose probe failed does not claim the disk is full', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      // Fail-closed free-space check: the disk may have ample capacity; the row
      // must diagnose the unreadable probe, not assert a full disk.
      monitor.observeStorageAtRisk(
        engagedAt: DateTime.now().subtract(const Duration(minutes: 30)),
        blockedCount: 2,
        retainedCount: 720,
        reason: 'disk_space_unknown',
      );

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.byKey(const Key('activity_attention_storage')), findsOneWidget);
      expect(find.text("Can't check storage"), findsOneWidget);
      expect(find.text('Phone storage full'), findsNothing, reason: 'an unavailable probe is not a proven full disk');
    });

    testWidgets('tapping the storage row opens Offline Sync once', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedStorage(monitor);
      final pushes = _PushCounter();

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor, observer: pushes));
      final baseline = pushes.count; // the MaterialApp's own initial route

      await tester.tap(find.text('Phone storage full'));
      expect(pushes.count - baseline, 1, reason: 'the row opens the Offline Sync entry exactly once');
    });

    testWidgets('a stalled pendant link lists a row that reconnects in place', (tester) async {
      var bleRetries = 0;
      // The automatic retry at declaration completes at once; the reader's retry is held in
      // flight so the row can be seen stepping aside while it runs.
      final held = Completer<void>();
      final monitor = CaptureWedgeMonitor(
        featureGate: () async => true,
        track: (_, __) {},
        bleRetry: (_) {
          bleRetries++;
          return bleRetries == 1 ? Future.value() : held.future;
        },
        appBuild: () => '1',
        platform: () => 'ios',
      );
      addTearDown(monitor.dispose);
      for (var i = 0; i < 3; i++) {
        final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
        monitor.onCaptureSessionEnded(handle, binaryBytesSent: 0);
      }
      await tester.pump();
      final pushes = _PushCounter();

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor, observer: pushes));
      final baseline = pushes.count;
      expect(find.byKey(const Key('activity_attention_capture_link')), findsOneWidget);
      expect(find.text("Omi isn't sending audio"), findsOneWidget);
      expect(find.text('Still recording on your Omi'), findsOneWidget);
      final retriesBefore = bleRetries;

      await tester.tap(find.text('Reconnect'));
      await tester.pump();
      expect(bleRetries, retriesBefore + 1, reason: 'the row retries the episode in place');
      expect(pushes.count - baseline, 0, reason: 'a stalled link is fixed where the reader stands');
      expect(find.byKey(const Key('activity_attention_capture_link')), findsNothing,
          reason: 'the row leaves while the retry runs');
      held.complete();
      await tester.pump();
    });

    testWidgets('an open storage episode does not hide a pendant stall', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedStorage(monitor);
      for (var i = 0; i < 3; i++) {
        final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
        monitor.onCaptureSessionEnded(handle, binaryBytesSent: 0);
      }
      await tester.pump();

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(monitor.acuteEpisode?.deviceId, 'dev-a');
      expect(find.byKey(const Key('activity_attention_capture_link')), findsOneWidget);
      expect(find.byKey(const Key('activity_attention_storage')), findsOneWidget);
    });

    testWidgets('a connected-but-silent pendant makes no still-recording claim', (tester) async {
      var now = DateTime(2026, 10, 19);
      final monitor = CaptureWedgeMonitor(
        now: () => now,
        featureGate: () async => true,
        track: (_, __) {},
        bleRetry: (_) async {},
        appBuild: () => '1',
        platform: () => 'ios',
      );
      monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      now = now.add(const Duration(minutes: 5));
      monitor.runConnectedWatchdog();
      await tester.pump();
      await tester.pump();

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(monitor.acuteEpisode?.trigger, CaptureWedgeMonitor.triggerConnectedNoBytes);
      expect(find.byKey(const Key('activity_attention_capture_link')), findsOneWidget);
      expect(find.text('Still recording on your Omi'), findsNothing,
          reason: 'nothing proves the pendant keeps live frames while it looks connected');
      // The open session's watchdog timer must not outlive the test.
      await tester.pumpWidget(const SizedBox());
      monitor.dispose();
    });

    testWidgets('an exhausted ingress recovery row explains, with no retry and no saved-audio claim', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
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
      await tester.pump();

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.byKey(const Key('activity_attention_capture_link')), findsOneWidget);
      expect(find.text('Reconnect'), findsNothing, reason: 'a Dart-side retry would no-op');
      expect(find.text('Still recording on your Omi'), findsNothing, reason: 'INV-CAP-1: no audio-saved claim');

      await tester.tap(find.byKey(const Key('activity_attention_capture_link')));
      await tester.pumpAndSettle();
      expect(find.textContaining('could not restore the connection automatically'), findsOneWidget,
          reason: 'the row opens the explanation');
    });

    testWidgets('an upload stall without known seconds shows only the count', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedUploadStall(monitor, pendingCount: 2, pendingSeconds: 0);

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.text('Upload stalled'), findsOneWidget);
      expect(find.text('2 recordings waiting'), findsOneWidget);
    });

    testWidgets('both rows together, ordered storage first with one divider each', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedStorage(monitor);
      _seedUploadStall(monitor);

      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.byKey(const Key('activity_needs_attention')), findsOneWidget);
      expect(
        tester.getTopLeft(find.byKey(const Key('activity_attention_storage'))).dy,
        lessThan(tester.getTopLeft(find.byKey(const Key('activity_attention_upload_stalled'))).dy),
      );
    });

    testWidgets('rows disappear when the monitor resolves them, taking the section with them', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedStorage(monitor);
      _seedUploadStall(monitor);
      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      expect(find.byKey(const Key('activity_needs_attention')), findsOneWidget);

      // Upload progress ends the stall row only; the storage row survives it.
      monitor.onUploadCompleted();
      await tester.pump();
      expect(find.byKey(const Key('activity_attention_upload_stalled')), findsNothing);
      expect(find.byKey(const Key('activity_attention_storage')), findsOneWidget);
      expect(find.byKey(const Key('activity_needs_attention')), findsOneWidget);

      monitor.clearStorageAtRisk();
      await tester.pump();
      expect(find.byKey(const Key('activity_attention_storage')), findsNothing);
      expect(find.byKey(const Key('activity_needs_attention')), findsNothing);
    });

    testWidgets('a cleared storage row ends the storage episode the capturing banner reads', (tester) async {
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      _seedStorage(monitor);
      await tester.pumpWidget(_app(const SizedBox(), monitor: monitor));
      await tester.pumpAndSettle();
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerStorageAtRisk,
          reason: 'the capturing page banner shows the storage problem');

      // The disk recovers: the row ends, and with it the episode — the banner
      // must stop reporting a recovered problem, and a later disk incident
      // must be able to declare a fresh episode.
      monitor.clearStorageAtRisk();
      await tester.pump();
      expect(monitor.visiblePrompt, isNull, reason: 'the banner stops reporting the recovered storage problem');

      _seedStorage(monitor);
      await tester.pumpAndSettle();
      expect(monitor.visiblePrompt?.trigger, CaptureWedgeMonitor.triggerStorageAtRisk,
          reason: 'a returning disk failure declares a fresh episode');
    });

    test('hasContent stays consistent with the rows', () async {
      final store = await _noWork();
      final idle = _IdleSync();
      final storage = _monitor();
      addTearDown(storage.dispose);
      expect(NeedsAttentionSection.hasContent(store, idle), isFalse);
      expect(NeedsAttentionSection.hasContent(store, idle, storage), isFalse);

      _seedStorage(storage);
      expect(NeedsAttentionSection.hasContent(store, idle, storage), isTrue);

      storage.onUploadCompleted();
      expect(NeedsAttentionSection.hasContent(store, idle, storage), isTrue,
          reason: 'the storage row survives uploads');
      storage.clearStorageAtRisk();
      expect(NeedsAttentionSection.hasContent(store, idle, storage), isFalse);

      // A finished upload arms the silence threshold's freshness guard, so the
      // stall case needs its own monitor.
      final upload = _monitor();
      addTearDown(upload.dispose);
      _seedUploadStall(upload);
      expect(NeedsAttentionSection.hasContent(store, idle, upload), isTrue);
    });
  });

  group('bell', () {
    testWidgets('unseen capture attention lights the warning dot and the semantics label', (tester) async {
      final store = await _noWork();
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      var stored = yesterday.millisecondsSinceEpoch;
      final seen = ActivitySeen(read: () => stored, write: (v) => stored = v, owner: () => 'u');

      _seedStorage(monitor);
      await tester.pumpWidget(pageApp(Scaffold(
        body: Center(child: ActivityBellButton(seen: seen, pendingWork: store, captureMonitor: monitor)),
      )));
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsOneWidget);
      expect(find.bySemanticsLabel('Activity, needs attention'), findsOneWidget);

      monitor.markCaptureAttentionSeen();
      await tester.pump();
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
    });

    testWidgets('a stalled pendant link lights the warning dot until audio flows again', (tester) async {
      final store = await _noWork();
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      var stored = yesterday.millisecondsSinceEpoch;
      final seen = ActivitySeen(read: () => stored, write: (v) => stored = v, owner: () => 'u');

      await tester.pumpWidget(pageApp(Scaffold(
        body: Center(child: ActivityBellButton(seen: seen, pendingWork: store, captureMonitor: monitor)),
      )));
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);

      for (var i = 0; i < 3; i++) {
        final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
        monitor.onCaptureSessionEnded(handle, binaryBytesSent: 0);
      }
      await tester.pump();
      await tester.pump();
      expect(monitor.acuteEpisode, isNotNull);
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsOneWidget,
          reason: 'Home has no banner, so the bell carries an acute stall');

      final handle = monitor.onCaptureSessionConnected(deviceId: 'dev-a', source: 'omi');
      monitor.onTranscriptObserved('dev-a');
      monitor.onCaptureSessionEnded(handle, binaryBytesSent: 64);
      await tester.pump();
      expect(monitor.acuteEpisode, isNull);
      expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing,
          reason: 'a resolved stall is no longer attention');
    });
  });

  group('ActivityPage', () {
    testWidgets('shows the capture rows and marks capture attention seen on load', (tester) async {
      final store = await _noWork();
      final monitor = _monitor();
      addTearDown(monitor.dispose);
      var stored = yesterday.millisecondsSinceEpoch;
      final seen = ActivitySeen(read: () => stored, write: (v) => stored = v, owner: () => 'u');
      _seedStorage(monitor);
      _seedUploadStall(monitor);
      expect(monitor.hasUnseenCaptureAttention.value, isTrue);

      await tester.pumpWidget(pageApp(ActivityPage(
        pendingWork: store,
        seen: seen,
        captureWedgeMonitor: monitor,
        probeDreamReport: () async => false,
        loadRecaps: () async => (items: <DailySummary>[], ok: true),
        loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])),
      )));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('activity_attention_storage')), findsOneWidget);
      expect(find.byKey(const Key('activity_attention_upload_stalled')), findsOneWidget);
      expect(monitor.hasUnseenCaptureAttention.value, isFalse,
          reason: 'opening Activity marks the capture rows seen; a new episode re-lights the bell');
    });
  });
}
