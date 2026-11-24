// V3 (recordings and conversations) outcomes, audit 2026-11-19 (v3-audit.md) and David's rulings of
// the same day: X5, X6, X7, X9, X10, X11, X14, X17, the Home row status line and swipe behavior.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversation_open.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/activity/activity_bell_button.dart';
import 'package:omi/pages/activity/past_processing_section.dart';
import 'package:omi/pages/conversation_detail/conversation_live_guard.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/pages/home/home_deep_links.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// The decoder fixture: a v3 conversation as the server sends it. [tile] null is a document with no
/// tile state (an older server).
ServerConversation _decoded(String? tile,
        {String id = 'c1', String status = 'completed', Map<String, dynamic> extra = const {}}) =>
    ServerConversation.fromJson({
      'id': id,
      'created_at': '2026-11-01T10:00:00Z',
      'started_at': '2026-11-01T10:00:00Z',
      'finished_at': '2026-11-01T10:12:00Z',
      'source': 'omi',
      'status': status,
      'structured': {'title': 'Planning the launch', 'overview': 'A synthetic summary', 'emoji': '🚀'},
      'transcript_segments': [
        {'id': 's1', 'text': 'Synthetic speech.', 'start': 0.0, 'end': 4.0, 'is_user': true},
      ],
      'kind': 'conversation',
      if (tile != null) 'tile_state': tile,
      ...extra,
    });

ConversationsV3Provider _v3(bool on) => ConversationsV3Provider(
    fetchLive: () async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    uid: () => 'u1',
    cached: 'u1:${on ? 1 : 0}');

PendingWorkStore _store({Future<ApiResult<PendingWorkSnapshot>> Function()? loadPending}) => PendingWorkStore(
      loadPending: loadPending ?? () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
      retry: (id, {required idempotencyKey}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
      retryAll: ({required idempotencyKey}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
      markSeen: (ids) async => const ApiSuccess(null),
    );

Widget _app(Widget home, {List<ChangeNotifierProvider> providers = const []}) {
  final app = MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: home,
  );
  return providers.isEmpty ? app : MultiProvider(providers: providers, child: app);
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _PhoneSync {
  int getInFlightSeconds() => 0;
  List<dynamic> getSessionUnsyncedWals(int start) => const [];
  List<dynamic> getSessionWals(int start) => const [];
  Future<void> finalizeCurrentSession() async {}
}

class _Syncs {
  final phone = _PhoneSync();
}

class _Wal implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// The active capture ID matches the live row's source recording.
class _Capture extends CaptureProvider {
  _Capture()
      : super(
          walService: _Wal(),
          connectivity: CaptureConnectivityBoundary(
            initiallyConnected: true,
            changes: const Stream.empty(),
            isConnected: () => true,
          ),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  @override
  String get activeRecordingId => 'capture-1';

  @override
  String get liveCaptureSource => 'omi';
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'u1'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('X5: a failed conversation leaves Home for Activity without lighting the bell', () {
    test('one predicate reads the tile state first, then the legacy fields', () {
      expect(isFailedConversation(_decoded('failed')), isTrue, reason: 'status completed, tile failed');
      expect(isFailedConversation(_decoded('done', status: 'failed')), isFalse, reason: 'the tile wins');
      expect(isFailedConversation(_decoded(null, status: 'failed')), isTrue, reason: 'no tile: legacy status');
      expect(isFailedConversation(_decoded(null)), isFalse);
    });

    // Tile state → (on Home, in Activity).
    const table = <(String, bool, bool)>[
      ('live', true, false),
      ('transcribing', true, false),
      ('writing', true, false),
      ('done', true, false),
      ('failed', false, true),
    ];

    test('Home and Activity, per tile state', () {
      for (final (tile, home, activity) in table) {
        final c = _decoded(tile);
        expect(shownOnV3Home(c), home, reason: '$tile on Home');
        expect(failedActivityConversations(pending: const [], conversations: [c], v3Only: true).isNotEmpty, activity,
            reason: '$tile in Activity');
      }
    });

    testWidgets('summary tile states do not light the bell', (tester) async {
      for (final (tile, _, _) in table) {
        final conversations = ConversationProvider(isSignedIn: () => false)..conversations = [_decoded(tile)];
        final store = _store();
        await tester.pumpWidget(_app(
          Scaffold(body: Center(child: ActivityBellButton(pendingWork: store))),
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<ConversationsV3Provider>.value(value: _v3(true)),
          ],
        ));
        expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing, reason: '$tile dot');
        await tester.pumpWidget(const SizedBox());
        conversations.dispose();
      }
    });
  });

  testWidgets('an unseen or dismissed summary failure does not light the bell', (tester) async {
    final conversations = ConversationProvider(isSignedIn: () => false)..conversations = [_decoded('failed')];
    final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage(
          enabled: true,
          items: [
            AttentionItem(
                id: 'a1',
                kind: 'conversation_summary_failed',
                conversationId: 'c1',
                retryable: true,
                seen: false,
                retryState: AttentionRetryState.none),
          ],
          unseenCount: 1)),
      dismiss: (_) async => const ApiSuccess(null),
      loadDismissed: (_) => const [],
      saveDismissed: (_, __) {},
    );
    await store.refresh();
    await tester.pumpWidget(_app(
      Scaffold(body: Center(child: ActivityBellButton(pendingWork: store))),
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<ConversationsV3Provider>.value(value: _v3(true)),
      ],
    ));
    expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
    await store.dismiss(store.attention.single);
    await tester.pump();
    expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    conversations.dispose();
  });

  test('X17: a failed pending-work read keeps the last good answer', () async {
    var fail = false;
    final store = _store(
      loadPending: () async => fail
          ? const ApiFailure(ApiProblem(ApiProblemKind.transport))
          : const ApiSuccess(
              PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)),
    );
    await store.refresh();
    expect(store.homeProcessingToday, isTrue);
    fail = true;
    await store.refresh();
    expect(store.homeProcessingToday, isTrue, reason: 'Activity lists stay; they are gated on it');
  });

  group('X6: a failed older page ends the list with one quiet line', () {
    test('the provider says so, and the next page clears it', () async {
      final first = [
        for (var i = 0; i < 50; i++)
          ServerConversation(
              id: 'r$i',
              createdAt: DateTime(2026, 11, 19, 10).subtract(Duration(minutes: i)),
              structured: Structured('t', ''))
      ];
      final provider =
          ConversationProvider(conversationListFetcher: () async => (items: first, ok: true), isSignedIn: () => true);
      addTearDown(provider.dispose);
      await provider.fetchConversations();
      expect(provider.hasMoreConversations, isTrue);

      provider.conversationPageFetcherOverride =
          () async => (items: <ServerConversation>[], ok: false, truncated: false);
      await provider.getMoreConversationsFromServer();
      expect(provider.loadMoreFailed, isTrue);

      provider.conversationPageFetcherOverride = () async => (
            items: [ServerConversation(id: 'older', createdAt: DateTime(2026, 11, 1), structured: Structured('t', ''))],
            ok: true,
            truncated: false
          );
      await provider.getMoreConversationsFromServer();
      expect(provider.loadMoreFailed, isFalse);
    });

    testWidgets('the line is text, tappable, with a spinner in its place while it retries', (tester) async {
      final retry = Completer<void>();
      var taps = 0;
      await tester.pumpWidget(_app(Scaffold(
        body: OmiLoadMoreFailed(onRetry: () {
          taps++;
          return retry.future;
        }),
      )));
      expect(find.text("Couldn't load older ones. Tap to retry."), findsOneWidget);
      expect(find.byType(OmiButton), findsNothing, reason: 'not button-styled');
      expect(tester.getSize(find.byType(OmiLoadMoreFailed)).height, greaterThanOrEqualTo(44));

      await tester.tap(find.byType(OmiLoadMoreFailed));
      await tester.pump(const Duration(milliseconds: 200));
      expect(find.byType(OmiSpinner), findsOneWidget);
      await tester.tap(find.byType(OmiLoadMoreFailed), warnIfMissed: false);
      expect(taps, 1, reason: 'one retry at a time');

      retry.complete();
      await tester.pumpAndSettle();
      expect(find.text("Couldn't load older ones. Tap to retry."), findsOneWidget);
    });
  });

  test('X7: Home re-reads its rows on the 15 s tick while one is transcribing or writing', () async {
    final v3 = _v3(true);
    addTearDown(v3.dispose);
    var rows = [_decoded('writing')];
    var reads = 0;
    v3.watch(
      rowsPending: () => ConversationsV3Provider.anyMidPipeline(rows),
      refreshRows: () async => reads++,
    );
    addTearDown(v3.unwatch);
    v3.tick();
    expect(reads, 1);
    rows = [_decoded('done')];
    v3.tick();
    expect(reads, 1, reason: 'nothing mid-pipeline: no list reads');
  });

  group('X9, X10: the processing page', () {
    testWidgets('repeated failed reads say so with Try Again; "still working" only after a read answered',
        (tester) async {
      var fail = true;
      await tester.pumpWidget(_app(FinishedCapturePage(
        recordingId: 'rec-1',
        pollInterval: const Duration(seconds: 1),
        maxWait: const Duration(seconds: 30),
        fetch: () async => fail ? throw Exception('offline') : <ServerConversation>[],
      )));
      await tester.pump();
      expect(find.text('Writing your summary…'), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(find.byKey(const Key('finished_capture_read_failed')), findsOneWidget);
      expect(find.text("Couldn't check on it. Try again."), findsOneWidget);

      fail = false;
      await tester.tap(find.text('Try Again'));
      await tester.pump();
      expect(find.byKey(const Key('finished_capture_processing')), findsOneWidget);

      await tester.pump(const Duration(seconds: 31));
      expect(find.text("Taking longer than usual. We'll have it on Home."), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  });

  testWidgets('X11: one predicate; a live conversation refuses changes and says why', (tester) async {
    final results = <bool>[];
    await tester.pumpWidget(_app(
      Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () {
              results
                ..add(refuseWhileLive(context, _decoded('live'), 'delete'))
                ..add(refuseWhileLive(context, _decoded('live'), 'copy_transcript'))
                ..add(refuseWhileLive(context, _decoded('done'), 'delete'));
            },
            child: const Text('go'),
          ),
        ),
      ),
      providers: [ChangeNotifierProvider<ConversationsV3Provider>.value(value: _v3(true))],
    ));
    await tester.tap(find.text('go'));
    await tester.pump();
    expect(results, [true, false, false]);
    expect(find.text('Wait until it ends to change it.'), findsOneWidget);
    expect(conversationIsLive(_decoded('live'), v3: false), isFalse, reason: 'not a v3 account');
    await tester.pump(const Duration(seconds: 9));
  });

  test('X14: the typed read keeps 404, 402 and an outage apart', () {
    expect(conversationOpenFrom(const ApiFailure(ApiProblem(ApiProblemKind.notFound))), isA<ConversationOpenGone>());
    expect(conversationOpenFrom(const ApiFailure(ApiProblem(ApiProblemKind.paymentRequired))),
        isA<ConversationOpenLocked>());
    expect(conversationOpenFrom(const ApiFailure(ApiProblem(ApiProblemKind.transport))),
        isA<ConversationOpenUnreachable>());
    expect(conversationOpenFrom(ApiSuccess(_decoded('done'))), isA<ConversationOpenFound>());
  });

  group('X14: a conversation link says what happened', () {
    for (final (answer, text) in <(ConversationOpen, String)>[
      (const ConversationOpenUnreachable(), "Can't connect right now."),
      (const ConversationOpenGone(), 'That conversation was deleted.'),
      (const ConversationOpenLocked(), 'Upgrade to open this one.'),
    ]) {
      testWidgets(text, (tester) async {
        late BuildContext home;
        await tester.pumpWidget(_app(Scaffold(body: Builder(builder: (context) {
          home = context;
          return const SizedBox();
        }))));
        final opened = await openHomeDeepLink(
          home,
          const HomeDeepLink('conversation', id: 'c1'),
          openSettings: () async {},
          conversationById: (_) async => answer,
          currentUid: () => 'u1',
        );
        await tester.pump();
        expect(opened, isFalse);
        expect(find.text(text), findsOneWidget);
        expect(find.textContaining('not found or deleted'), findsNothing);
        expect(find.text('Try Again'), answer is ConversationOpenUnreachable ? findsOneWidget : findsNothing);
        await tester.pump(const Duration(seconds: 9));
      });
    }
  });

  group('Home rows on v3', () {
    Future<ConversationProvider> pumpRow(WidgetTester tester, ServerConversation c, {CaptureProvider? capture}) async {
      final provider = ConversationProvider(isSignedIn: () => false)..conversations = [c];
      addTearDown(provider.dispose);
      await tester.pumpWidget(_app(
        Scaffold(body: ConversationListItem(conversation: c, date: DateTime(2026, 11, 19), conversationIdx: 0)),
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(value: provider),
          ChangeNotifierProvider<ConversationsV3Provider>.value(value: _v3(true)),
          ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
          if (capture != null) ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ],
      ));
      await tester.pump();
      return provider;
    }

    testWidgets('transcribing and writing say so under the title, with no button', (tester) async {
      await pumpRow(tester, _decoded('transcribing'));
      expect(find.text('Transcribing…'), findsOneWidget);
      expect(find.byType(OmiButton), findsNothing);
      await pumpRow(tester, _decoded('writing'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Writing summary…'), findsOneWidget);
      await pumpRow(tester, _decoded('live'));
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('Listening'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the tile and the line change in place, cross-fading', (tester) async {
      Widget tileFor(String tile) => ConversationStateTile(conversation: _decoded(tile));
      Widget host(String tile) => ChangeNotifierProvider<ConversationsV3Provider>.value(
            value: _v3(true),
            child: _app(Scaffold(body: Center(child: tileFor(tile)))),
          );
      await tester.pumpWidget(host('transcribing'));
      await tester.pumpWidget(host('writing'));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byKey(const Key('conversation_tile_transcribing')), findsOneWidget, reason: 'fading out');
      expect(find.byKey(const Key('conversation_tile_writing')), findsOneWidget, reason: 'fading in');
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byKey(const Key('conversation_tile_transcribing')), findsNothing);
    });

    Future<void> swipe(WidgetTester tester, double dx) async {
      final gesture = await tester.startGesture(tester.getCenter(find.byKey(const ValueKey('conversation_card'))));
      for (var i = 0; i < 12; i++) {
        await gesture.moveBy(Offset(dx / 12, 0));
        await tester.pump(const Duration(milliseconds: 16));
      }
      await gesture.up();
      // The live dot breathes forever: settle by time, not pumpAndSettle.
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump(const Duration(milliseconds: 400));
    }

    testWidgets('a live row this phone is capturing does not swipe or expose Finish', (tester) async {
      final capture = _Capture();
      addTearDown(capture.dispose);
      await pumpRow(
          tester,
          _decoded('live', extra: {
            'v3_recording_ids': [capture.activeRecordingId],
          }),
          capture: capture);
      final card = find.byKey(const ValueKey('conversation_card'));
      final rest = tester.getRect(card);
      await swipe(tester, -200);
      expect(tester.getRect(card), rest);
      expect(find.text('Finish'), findsNothing);
      expect(find.byKey(const ValueKey('conversation_swipe_finish')), findsNothing);
      expect(find.byKey(const ValueKey('conversation_swipe_delete')), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a live row another device is capturing does not swipe', (tester) async {
      await pumpRow(tester, _decoded('live'));
      final rest = tester.getRect(find.byKey(const ValueKey('conversation_card')));
      await swipe(tester, -200);
      expect(tester.getRect(find.byKey(const ValueKey('conversation_card'))), rest, reason: 'it does not move');
      expect(find.byKey(const ValueKey('conversation_swipe_finish')), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });
  });
}
