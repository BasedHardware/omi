import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/episodes/finish_capture.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/finish_outcome.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

// Nik, 2026-11-18 (TestFlight 1.0.593, pendant, v3): Finish on the live page did nothing and went
// back to the list; the conversation showed up 4 minutes later. A batch pendant's page shows only
// the on-device preview, never `segments`, so Finish took the "nothing heard" branch. Finish must
// process it and open the conversation itself, in a processing state until the server has it.

class _ManualFinishConversations extends ConversationProvider {
  _ManualFinishConversations() : super(isSignedIn: () => false);

  int refreshes = 0;

  @override
  Future<void> forceRefreshConversations() async {
    refreshes++;
  }
}

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
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

/// The on-device preview as the live page reads it: its lines and its running word count.
class _Preview extends ChangeNotifier implements LivePreviewController {
  _Preview(this.lines, this.totalWordsSeen);

  @override
  final List<LivePreviewLine> lines;

  @override
  int totalWordsSeen;

  @override
  int get sessionGeneration => 1;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends CaptureProvider {
  _Capture({this.preview, this.closed, this.answer, this.answerDelay})
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

  final LivePreviewController? preview;
  final ({String id, DateTime at, int previewWords, int previewSession})? closed;
  CreateConversationResponse? answer;
  final Future<void>? answerDelay;
  var finishes = 0;
  ProcessAbsence failure = ProcessAbsence.transport;

  @override
  String? verifiedLiveServerRecordingId;

  /// The page renders the preview; this fake only answers what Finish reads, so it is handed over
  /// at the tap.
  bool tapped = false;

  @override
  LivePreviewController? get livePreview => tapped ? preview : null;

  @override
  ({String id, DateTime at, int previewWords, int previewSession})? get lastServerClose => closed;

  @override
  void noteClientFinish() => lastClientFinish = (
        at: DateTime.now(),
        previewWords: preview?.totalWordsSeen ?? 0,
        previewSession: preview?.sessionGeneration ?? 0,
      );

  @override
  String? get liveCaptureSource => 'omi';

  @override
  Future<InProgressProcessOutcome> finishCaptureWithOutcome() async {
    finishes++;
    await answerDelay;
    final reply = answer;
    return InProgressProcessOutcome(response: reply, absence: reply == null ? failure : null);
  }
}

Map<String, dynamic> _row(String id, {String createdAt = '2026-11-18T22:00:09Z', Map<String, dynamic>? extra}) => {
      'id': id,
      'created_at': createdAt,
      'started_at': createdAt,
      'finished_at': '2026-11-18T22:19:35Z',
      'source': 'omi',
      'status': 'completed',
      'structured': {'title': 'Fundraising call', 'overview': 'A synthetic summary', 'emoji': '📞'},
      'transcript_segments': [
        {'text': 'Synthetic speech.', 'start': 0.0, 'end': 4.0, 'is_user': true},
      ],
      ...?extra,
    };

ServerConversation _conversation(String id, {String createdAt = '2026-11-18T22:00:09Z', Map<String, dynamic>? extra}) =>
    ServerConversation.fromJson(_row(id, createdAt: createdAt, extra: extra));

ServerConversation _derived(String id, String recordingId, {String createdAt = '2026-11-18T22:00:09Z'}) =>
    _conversation(
      id,
      createdAt: createdAt,
      extra: {
        'kind': 'conversation',
        'tile_state': 'writing',
        'recording_pieces': [
          {'recording_id': recordingId, 'audio_file_id': 'a1', 'start': 0.0, 'end': 600.0},
        ],
      },
    );

/// The recording document Process Now answers with: processing once admitted, still in progress when
/// the server found nothing to process in it.
ServerConversation _recordingDoc(String id, {bool notProcessed = false}) => _conversation(
      id,
      extra: {
        'recording': true,
        'status': notProcessed ? 'in_progress' : 'processing',
        'structured': {'title': ''},
      },
    );

const _line = LivePreviewLine(id: 'l1', text: 'We closed the round', isFinal: true);

class _Harness {
  _Harness(this.home, this.capture);
  final HomeProvider home;
  final _Capture capture;
}

Future<_Harness> _pump(WidgetTester tester, _Capture capture, {ConversationsV3Provider? v3}) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final home = HomeProvider()..setIndex(HomeProvider.tasksTab);
  final device = _StubDeviceProvider();
  final connectivity = _StubConnectivityProvider();
  final usage = UsageProvider();
  addTearDown(home.dispose);
  addTearDown(capture.dispose);
  addTearDown(device.dispose);
  addTearDown(connectivity.dispose);
  addTearDown(usage.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        if (v3 != null) ChangeNotifierProvider<ConversationsV3Provider>.value(value: v3),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
      ],
      child: MaterialApp(
        theme: ThemeData.dark(),
        locale: const Locale('en'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const LiveEpisodePage())),
                child: const Text('home'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('home'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  expect(find.byType(LiveEpisodePage), findsOneWidget);
  return _Harness(home, capture);
}

/// Records the page Finish replaced the live page with, without building it.
Future<Widget?> _finishAndCapturePushed(WidgetTester tester, _Capture capture) async {
  final dynamic state = tester.state(find.byType(LiveEpisodePage));
  capture.tapped = true;
  await (state.debugStopConversation(capture) as Future<void>);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  // The replacement is built on the next frame; read the route's page before the test tears down.
  final finished = find.byType(FinishedCapturePage);
  if (finished.evaluate().isNotEmpty) return tester.widget(finished);
  return null;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a batch pendant Finish with only preview lines processes the capture', (tester) async {
    final harness = await _pump(
      tester,
      _Capture(
        preview: _Preview(const [_line], 4),
        answer: CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1')),
      ),
    );

    final page = await _finishAndCapturePushed(tester, harness.capture) as FinishedCapturePage?;

    expect(harness.capture.finishes, 1, reason: 'the preview is what this page shows; it is something to process');
    expect(harness.home.selectedIndex, HomeProvider.homeTab);
    expect(page?.recordingId, 'rec-1', reason: 'v3 answers with the recording; wait for its conversation');
    expect(find.byKey(const Key('finished_capture_processing')), findsOneWidget);
    expect(find.text('Writing your summary…'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(LiveEpisodePage), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  test('the conversation Process Now returns opens its own page; a recording waits; none goes Home', () {
    Widget? pageFor(ServerConversation? conversation) => finishedPageFor(FinishOutcome.fromProcess(
        InProgressProcessOutcome(
          response:
              conversation == null ? null : CreateConversationResponse(messages: const [], conversation: conversation),
        ),
        heardSomething: true));
    final page = pageFor(_conversation('c-1'));
    expect(page, isA<ConversationDetailPage>());
    expect((page as ConversationDetailPage).conversation.id, 'c-1');
    expect((pageFor(_recordingDoc('rec-1')) as FinishedCapturePage).recordingId, 'rec-1');
    expect(pageFor(null), isNull);
    expect(pageFor(_conversation('c-2', extra: {'discarded': true})), isNull);
  });

  testWidgets('Finish right after the server closed the recording opens that one', (tester) async {
    final harness = await _pump(
      tester,
      _Capture(
        preview: _Preview(const [_line], 4),
        closed: (
          id: 'rec-closed',
          at: DateTime.now().subtract(const Duration(seconds: 3)),
          previewWords: 4,
          previewSession: 1,
        ),
      ),
    );

    final page = await _finishAndCapturePushed(tester, harness.capture) as FinishedCapturePage?;

    expect(harness.capture.finishes, 0, reason: 'nothing was heard since; the new recording is empty');
    expect(page?.recordingId, 'rec-closed');
    expect(harness.home.selectedIndex, HomeProvider.homeTab);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('with nothing heard, Finish says so and returns to the page it came from', (tester) async {
    final harness = await _pump(tester, _Capture(preview: _Preview(const [], 0)));

    final dynamic state = tester.state(find.byType(LiveEpisodePage));
    harness.capture.tapped = true;
    await (state.debugStopConversation(harness.capture) as Future<void>);
    await tester.pump();

    expect(harness.capture.finishes, 0);
    expect(find.text('Nothing new yet.'), findsWidgets);
    expect(harness.home.selectedIndex, HomeProvider.tasksTab);
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(LiveEpisodePage), findsNothing);
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('a double tap on Finish sends one request and opens one page', (tester) async {
    final answer = Completer<void>();
    final harness = await _pump(
      tester,
      _Capture(
        preview: _Preview(const [_line], 4),
        answer: CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1')),
        answerDelay: answer.future,
      ),
    );
    final dynamic state = tester.state(find.byType(LiveEpisodePage));
    harness.capture.tapped = true;
    final first = state.debugStopConversation(harness.capture) as Future<void>;
    await tester.pump();
    final second = state.debugStopConversation(harness.capture) as Future<void>;
    await tester.pump();
    expect(find.byType(LiveEpisodePage), findsOneWidget, reason: 'the second tap must not pop Home in');
    answer.complete();
    await Future.wait([first, second]);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(harness.capture.finishes, 1);
    expect(find.byType(FinishedCapturePage), findsOneWidget);
    expect(find.text('home'), findsNothing, reason: 'Home stays under the Processing page');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a Finish that failed offline stays on the page and the next Finish sends it again', (tester) async {
    final harness = await _pump(tester, _Capture(preview: _Preview(const [_line], 4)));
    // Offline: Process Now has no answer. The reader stays on the live page with Try Again (C1).
    final first = await _finishAndCapturePushed(tester, harness.capture);
    expect(harness.capture.finishes, 1);
    expect(first, isNull);
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(LiveEpisodePage), findsOneWidget, reason: 'never a silent pop to Home (C1, X2)');
    expect(find.text("Didn't go through. Your audio is safe."), findsOneWidget, reason: 'an error, not silence (X2)');
    expect(find.text('Try Again'), findsOneWidget);

    // Back online, same preview lines, no new words: the retry still has something to process.
    harness.capture.answer = CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1'));
    final second = await _finishAndCapturePushed(tester, harness.capture) as FinishedCapturePage?;

    expect(harness.capture.finishes, 2, reason: 'the failed Finish processed nothing');
    expect(second?.recordingId, 'rec-1');
    expect(find.text('Nothing new yet.'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Finish again with no new speech sends nothing and says so', (tester) async {
    final preview = _Preview(const [_line], 4);
    final harness = await _pump(
      tester,
      _Capture(
        preview: preview,
        answer: CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1')),
      ),
    );
    await _finishAndCapturePushed(tester, harness.capture);
    expect(harness.capture.finishes, 1);

    // The reader reopens the live page; the preview still shows the same lines.
    final nav = Navigator.of(tester.element(find.byType(FinishedCapturePage)));
    unawaited(nav.pushReplacement(MaterialPageRoute<void>(builder: (_) => const LiveEpisodePage())));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    final dynamic state = tester.state(find.byType(LiveEpisodePage));
    await (state.debugStopConversation(harness.capture) as Future<void>);
    await tester.pump();

    expect(harness.capture.finishes, 1, reason: 'no new words since the last Finish');
    expect(find.text('Nothing new yet.'), findsWidgets);
    expect(find.byType(FinishedCapturePage), findsNothing);

    await tester.pump(const Duration(seconds: 5));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a recording the server has none of yet says so, keeps the page, and does not wait', (tester) async {
    final harness = await _pump(
      tester,
      _Capture(
        preview: _Preview(const [_line], 4),
        answer: CreateConversationResponse(
          messages: const [],
          conversation: _recordingDoc('rec-empty', notProcessed: true),
        ),
      ),
    );
    final page = await _finishAndCapturePushed(tester, harness.capture);

    expect(harness.capture.finishes, 1);
    expect(page, isNull, reason: 'no conversation will come from it yet');
    // C5 (audit 2026-11-19): the page shows words, so "Nothing to process yet" was false.
    expect(find.text('Nothing new yet.'), findsNothing);
    expect(find.text("Audio's still on its way."), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(LiveEpisodePage), findsOneWidget, reason: 'the recording carries on');
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('v3 Wrap Up returns to the published Home processing row', (tester) async {
    final v3 = ConversationsV3Provider(uid: () => 'owner', cached: 'owner:1');
    addTearDown(v3.dispose);
    final recording = _recordingDoc('rec-1');
    final capture = _Capture(answer: CreateConversationResponse(messages: const [], conversation: recording))
      ..verifiedLiveServerRecordingId = recording.id;
    await _pump(tester, capture, v3: v3);
    final row = OptimisticProcessingPlaceholder.conversation();
    v3.startManualFinish(row, recording.id);
    v3.settleManualFinish(row, recording);

    expect(await _finishAndCapturePushed(tester, capture), isNull);
    expect(capture.finishes, 1);
    expect(find.text('home'), findsOneWidget);
    expect(v3.finishRow, same(row));
    // Keep the fixture's fake clock and use an explicit terminal settlement before teardown.
    v3.acknowledgeManualFinish(row);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('v3 Wrap Up sends a verified pendant finish with no transcript and explains a 404', (tester) async {
    final v3 = ConversationsV3Provider(uid: () => 'owner', cached: 'owner:1');
    addTearDown(v3.dispose);
    final capture = _Capture()
      ..verifiedLiveServerRecordingId = 'rec-1'
      ..failure = ProcessAbsence.notFound;
    await _pump(tester, capture, v3: v3);

    expect(await _finishAndCapturePushed(tester, capture), isNull);
    expect(capture.finishes, 1);
    expect(find.byType(LiveEpisodePage), findsOneWidget);
    expect(find.text("Didn't go through. Your audio is safe."), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the shared Home finish helper classifies a v3 404 as a failure', (tester) async {
    final v3 = ConversationsV3Provider(uid: () => 'owner', cached: 'owner:1');
    addTearDown(v3.dispose);
    final capture = _Capture()
      ..verifiedLiveServerRecordingId = 'rec-1'
      ..failure = ProcessAbsence.notFound;
    await _pump(tester, capture, v3: v3);
    final navigator = Navigator.of(tester.element(find.byType(LiveEpisodePage)));
    navigator.pop();
    await tester.pumpAndSettle();

    final outcome = await finishLiveCapture(tester.element(find.text('home')), capture);
    expect(outcome, isA<FinishFailed>());
    expect(capture.finishes, 1);
    await tester.pumpWidget(const SizedBox());
  });

  for (final absence in [ProcessAbsence.notFound, ProcessAbsence.emptyBody, ProcessAbsence.transport, null]) {
    testWidgets('detached v3 finish shows the typed message for $absence', (tester) async {
      var liveReads = 0;
      final v3 = ConversationsV3Provider(
        uid: () => 'owner',
        cached: 'owner:1',
        fetchLive: () async {
          liveReads++;
          return const ApiSuccess(ConversationsLiveRead(v3: true, conversation: null));
        },
      );
      final conversations = _ManualFinishConversations();
      final messages = MessageProvider();
      final people = PeopleProvider();
      final usage = UsageProvider();
      addTearDown(v3.dispose);
      addTearDown(conversations.dispose);
      addTearDown(messages.dispose);
      addTearDown(people.dispose);
      addTearDown(usage.dispose);
      final actions = ProviderCaptureExternalActions(
        conversationProvider: conversations,
        messageProvider: messages,
        peopleProvider: people,
        usageProvider: usage,
        conversationsV3: v3,
      );
      await tester.pumpWidget(MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: const Scaffold(body: Text('Home')),
      ));

      final row = OptimisticProcessingPlaceholder.conversation();
      actions.onManualFinishStarted(row, 'rec-1');
      if (absence == ProcessAbsence.transport) {
        await tester.pump(OptimisticProcessingPlaceholder.timeout);
        expect(v3.finishRow, isNull, reason: 'an unresolved row stops displaying after its deadline');
      }
      final response = absence == null
          ? CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1', notProcessed: true))
          : null;
      actions.onManualFinishSettled(row, InProgressProcessOutcome(response: response, absence: absence),
          showFailure: true);
      await tester.pump();
      final message = switch (absence) {
        ProcessAbsence.emptyBody => 'That recording was too short or empty to keep.',
        null => "Audio's still on its way.",
        _ => "Didn't go through. Your audio is safe.",
      };
      expect(find.text(message), findsOneWidget);
      expect(conversations.refreshes, 1);
      expect(liveReads, 1);
      expect(v3.finishRow, isNull);
      await tester.pump(const Duration(seconds: 10));
      await tester.pumpWidget(const SizedBox());
    });
  }

  group('FinishedCapturePage', () {
    test('matches the derived conversation, never the recording or an unrelated sync copy', () {
      final rows = [
        _conversation('3d2eea45-sync-piece'), // #25728: same span, no piece of the recording
        _recordingDoc('rec-1'),
        _derived('714c4186', 'rec-1'),
        _derived('other', 'rec-2'),
      ];
      expect(FinishedCapturePage.match(rows, 'rec-1')?.id, '714c4186');
      expect(FinishedCapturePage.match(rows, 'rec-3'), isNull);
    });

    test('of several conversations from one recording it opens the newest, the top Home row', () {
      final rows = [
        _derived('first', 'rec-1', createdAt: '2026-11-18T22:00:09Z'),
        _derived('second', 'rec-1', createdAt: '2026-11-18T22:12:00Z'),
      ];
      expect(FinishedCapturePage.match(rows, 'rec-1')?.id, 'second');
    });

    test('before v3 the conversation is matched by its own id', () {
      expect(FinishedCapturePage.match([_conversation('c-1')], 'c-1')?.id, 'c-1');
    });

    Widget pageApp(Widget page, {HomeProvider? home}) => ChangeNotifierProvider<HomeProvider>.value(
          value: home ?? HomeProvider(),
          child: MaterialApp(
            locale: const Locale('en'),
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: AppLocalizations.supportedLocales,
            home: Builder(
              builder: (context) => TextButton(
                onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page)),
                child: const Text('home'),
              ),
            ),
          ),
        );

    testWidgets('after the wait it stops and says it will appear on Home, with Back to Home', (tester) async {
      var reads = 0;
      final home = HomeProvider()..setIndex(HomeProvider.tasksTab);
      addTearDown(home.dispose);
      await tester.pumpWidget(
        pageApp(
          FinishedCapturePage(
            recordingId: 'rec-1',
            maxWait: const Duration(seconds: 12),
            fetch: () async {
              reads++;
              return const [];
            },
            open: (_, __) => fail('nothing to open'),
          ),
          home: home,
        ),
      );
      await tester.tap(find.text('home'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byKey(const Key('finished_capture_processing')), findsOneWidget);

      await tester.pump(const Duration(seconds: 15));
      expect(find.byKey(const Key('finished_capture_expired')), findsOneWidget);
      expect(find.text("Taking longer than usual. We'll have it on Home."), findsOneWidget);
      final readsAtExpiry = reads;
      await tester.pump(const Duration(seconds: 30));
      expect(reads, readsAtExpiry, reason: 'no polling after it gave up');

      expect(home.selectedIndex, HomeProvider.tasksTab);
      await tester.tap(find.text('Back to Home'));
      await tester.pumpAndSettle();
      expect(find.byType(FinishedCapturePage), findsNothing);
      expect(home.selectedIndex, HomeProvider.homeTab);
    });

    testWidgets('a resume after the wait still reads once and opens it', (tester) async {
      var ready = false;
      ServerConversation? opened;
      await tester.pumpWidget(
        pageApp(
          FinishedCapturePage(
            recordingId: 'rec-1',
            pollInterval: const Duration(seconds: 10),
            maxWait: const Duration(seconds: 12),
            fetch: () async => ready ? [_derived('714c4186', 'rec-1')] : const [],
            open: (_, conversation) => opened = conversation,
          ),
        ),
      );
      await tester.tap(find.text('home'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 25));
      expect(find.byKey(const Key('finished_capture_expired')), findsOneWidget);

      ready = true;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(opened?.id, '714c4186');
    });

    testWidgets('waits, then opens the conversation as soon as it is listed', (tester) async {
      var reads = 0;
      ServerConversation? opened;
      await tester.pumpWidget(
        MaterialApp(
          locale: const Locale('en'),
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: FinishedCapturePage(
            recordingId: 'rec-1',
            fetch: () async => ++reads < 3 ? [_conversation('3d2eea45-sync-piece')] : [_derived('714c4186', 'rec-1')],
            open: (_, conversation) => opened = conversation,
          ),
        ),
      );
      await tester.pump();
      expect(find.text('Writing your summary…'), findsOneWidget);
      expect(opened, isNull);

      await tester.pump(const Duration(seconds: 5));
      expect(opened, isNull);
      await tester.pump(const Duration(seconds: 5));
      expect(opened?.id, '714c4186');
      final readsWhenOpened = reads;
      await tester.pump(const Duration(seconds: 15));
      expect(reads, readsWhenOpened, reason: 'polling stops once it opened');
      await tester.pumpWidget(const SizedBox());
    });
  });
}
