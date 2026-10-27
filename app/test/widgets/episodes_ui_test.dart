import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/episode_moments_section.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/pages/episodes/previous_episode_link.dart';
import 'package:omi/pages/settings/device/device_live_sections.dart';
import 'package:omi/pages/settings/device/device_catching_up_card.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

import '../support/live_preview_fakes.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/widgets/transcript.dart';

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
}

class _WalService implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Syncs {
  final phone = _PhoneSync();
}

/// A pendant capture in progress; nothing reaches the device or the network.
class _LiveCapture extends CaptureProvider {
  _LiveCapture()
      : super(
          walService: _WalService(),
          connectivity: CaptureConnectivityBoundary(
            initiallyConnected: true,
            changes: const Stream.empty(),
            isConnected: () => true,
          ),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  String source = 'omi';

  LivePreviewController? preview;
  bool previewAdmitted = false;

  @override
  LivePreviewController? get livePreview => preview;

  @override
  bool get localPreviewAdmitted => previewAdmitted;

  @override
  String? get liveCaptureSource => source;

  @override
  String? get topConversationId => 'c1';

  String? recordingId;

  @override
  String? get activeRecordingId => recordingId;

  DateTime? _startedAt;
  set startedAt(DateTime? value) {
    _startedAt = value;
    notifyListeners();
  }

  @override
  DateTime? get liveCaptureStartedAt => _startedAt;
}

final _now = DateTime(2026, 10, 20, 12, 30);

TranscriptSegment _segment(String id, String text, double start) => TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_0',
      isUser: true,
      personId: null,
      translations: [],
      start: start,
      end: start + 20,
    );

Episode _liveEpisode({List<EpisodeItem>? items}) => Episode(
      id: 'ep1',
      live: true,
      startedAt: _now.subtract(const Duration(minutes: 24)),
      lastActivityAt: _now,
      title: 'Lunch plans with Maya',
      bullets: const ['Picking a place near the office', 'Maya prefers somewhere quiet'],
      people: const ['Maya'],
      items: items ??
          [
            EpisodeItem(
              id: 'i1',
              text: 'Book a table for Friday',
              createdAt: _now.subtract(const Duration(minutes: 3)),
              conversationId: 'c1',
              segmentOffset: 70,
            ),
          ],
      moments: [
        EpisodeMoment(
          id: 'm1',
          conversationId: 'c1',
          startedAt: _now.subtract(const Duration(minutes: 24)),
          endedAt: _now.subtract(const Duration(minutes: 10)),
          startOffset: 0,
          endOffset: 50,
          heading: 'Where to eat',
        ),
        EpisodeMoment(
          id: 'm2',
          conversationId: 'c1',
          startedAt: _now.subtract(const Duration(minutes: 9)),
          endedAt: _now,
          startOffset: 60,
          endOffset: 120,
          heading: 'Booking',
        ),
      ],
      conversationIds: const ['c1'],
      stateUpdatedAt: _now.subtract(const Duration(minutes: 2)),
    );

class _PausableCapture extends _LiveCapture {
  bool paused = false;
  int pauses = 0;
  int resumes = 0;

  @override
  bool get isPaused => paused;

  @override
  Future<void> pauseCapture() async => pauses++;

  @override
  Future<void> resumeCapture() async {
    resumes++;
    paused = false;
    notifyListeners();
  }
}

/// A pendant whose native ingress health the test drives directly.
class _IngressCapture extends _LiveCapture {
  _IngressCapture({this.verified = true, this.actionRequired = false});

  bool verified;
  bool actionRequired;
  int reconnects = 0;

  @override
  bool get pendantCaptureVerified => verified;

  @override
  bool get pendantCaptureActionRequired => actionRequired;

  @override
  Future<void> reconnectRecordingPendant() async => reconnects++;
}

EpisodeProvider _episodes({Episode? live, bool enabled = true, List<String>? dismissed, DateTime Function()? clock}) {
  final provider = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: enabled, episode: live)),
    lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async {
      dismissed?.add(itemId);
      return const ApiFailure(ApiProblem(ApiProblemKind.transport));
    },
    clock: clock ?? () => _now,
  );
  provider.debugSetLive(live, enabled: enabled);
  return provider;
}

Future<void> _pump(
  WidgetTester tester,
  Widget home, {
  required CaptureProvider capture,
  EpisodeProvider? episodes,
}) async {
  tester.view.physicalSize = const Size(800, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final device = _StubDeviceProvider();
  final usage = UsageProvider();
  addTearDown(device.dispose);
  addTearDown(usage.dispose);
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        if (episodes != null) ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
        ChangeNotifierProvider(
          create: (_) => PeopleProvider(loadPeople: () async => const PeopleListResponse(people: [])),
        ),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>(create: (_) => _StubConnectivityProvider()),
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
        home: home,
      ),
    ),
  );
  await tester.pump();
}

Future<void> _unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('live episode page', () {
    testWidgets('no server episode waits briefly, then names unavailable notes without resetting capture time', (
      tester,
    ) async {
      final clock = tester.binding.clock;
      final start = clock.now();
      final capture = _LiveCapture()..startedAt = start;
      final episodes = _episodes(clock: clock.now);
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      expect(find.text('Running notes appear after the first few minutes of talk.'), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Capturing · 0s');
      await tester.pump(const Duration(minutes: 3));
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      expect(find.text('Running notes appear after the first few minutes of talk.'), findsNothing);
      expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Capturing · 3m');
      await _unmount(tester);
    });

    testWidgets('an old empty server episode cannot renew the initial notes promise', (tester) async {
      final capture = _LiveCapture();
      final episode = Episode(
        id: 'empty',
        live: true,
        startedAt: _now.subtract(const Duration(minutes: 4)),
        lastActivityAt: _now,
        stateUpdatedAt: _now,
      );
      final episodes = _episodes(live: episode);
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      expect(find.text('Running notes appear after the first few minutes of talk.'), findsNothing);
      await _unmount(tester);
    });

    testWidgets('a new recording gets its own wait and timer; reconnects keep its deadline', (tester) async {
      final clock = tester.binding.clock;
      final capture = _LiveCapture()
        ..source = 'phone'
        ..recordingState = RecordingState.record
        ..recordingId = 'first'
        ..startedAt = clock.now();
      final episodes = _episodes(clock: clock.now);
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      await tester.pump(const Duration(minutes: 4));
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      capture
        ..recordingId = 'second'
        ..startedAt = clock.now();
      await tester.pump();
      expect(find.byKey(const Key('episode_notes_unavailable')), findsNothing);
      expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Capturing · 0s');
      await tester.pump(const Duration(minutes: 2));
      // A newer ingress timestamp for the same capture must not renew the promise or clock.
      capture.startedAt = clock.now();
      await tester.pump();
      await tester.pump(const Duration(minutes: 1));
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Capturing · 3m');
      await _unmount(tester);
    });

    testWidgets('the open previous episode adopts delayed closure and finalization by ID', (tester) async {
      final pending = Completer<ApiResult<EpisodeRead>>();
      var firstRead = true;
      Episode closed = Episode(
        id: 'ep1',
        live: false,
        startedAt: _liveEpisode().startedAt,
        lastActivityAt: _now,
        title: 'Recovered title',
        bullets: const ['Recovered note'],
        conversationIds: const ['c1'],
      );
      final capture = _LiveCapture();
      final episodes = EpisodeProvider(
        clock: () => _now,
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        lookup: (_) {
          if (firstRead) {
            firstRead = false;
            return pending.future;
          }
          return Future.value(ApiSuccess(EpisodeRead(enabled: true, episode: closed)));
        },
      )..debugSetLive(_liveEpisode());
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const Scaffold(body: PreviousEpisodeLink()), capture: capture, episodes: episodes);
      await tester.tap(find.text('Continues “Lunch plans with Maya”'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(find.text('Picking a place near the office'), findsOneWidget);
      pending.complete(ApiSuccess(EpisodeRead(enabled: true, episode: closed)));
      await tester.pump();
      await tester.pump();
      expect(find.text('Recovered note'), findsOneWidget);
      expect(find.text('Picking a place near the office'), findsNothing);
      // A newer closed episode must not redirect the already-open page.
      episodes.debugSetLive(Episode(
        id: 'newer',
        live: false,
        startedAt: _now,
        lastActivityAt: _now,
        title: 'Newer episode',
      ));
      closed = Episode(
        id: 'ep1',
        live: false,
        startedAt: _liveEpisode().startedAt,
        lastActivityAt: _now,
        title: 'Final title',
        bullets: const ['Final note'],
        moments: _liveEpisode().moments,
        conversationIds: const ['c1'],
      );
      await tester.pump(EpisodeProvider.pollInterval);
      await tester.pump();
      expect(find.text('Final note'), findsOneWidget);
      expect(find.textContaining('Where to eat'), findsOneWidget);
      expect(find.text('Final title'), findsOneWidget);
      expect(episodes.previous?.id, 'newer');
      await _unmount(tester);
    });

    testWidgets('an already old capture never starts another first-few-minutes promise', (tester) async {
      final capture = _LiveCapture()..startedAt = _now.subtract(const Duration(minutes: 88));
      final episodes = _episodes();
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      expect(find.text('Running notes appear after the first few minutes of talk.'), findsNothing);
      expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Capturing · 1h 28m 0s');
      await _unmount(tester);
    });

    testWidgets('stale notes stay readable with an explicit warning; fresh server state recovers', (tester) async {
      final clock = tester.binding.clock;
      final start = clock.now();
      final capture = _LiveCapture()..startedAt = start;
      Episode? live = Episode(
        id: 'stale',
        live: true,
        startedAt: start,
        lastActivityAt: start,
        stateUpdatedAt: start,
        bullets: const ['Retained note'],
      );
      var failed = false;
      final episodes = EpisodeProvider(
        clock: clock.now,
        fetchLive: () async => failed
            ? const ApiFailure(ApiProblem(ApiProblemKind.transport))
            : ApiSuccess(EpisodeRead(enabled: true, episode: live)),
      )..debugSetLive(live);
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      failed = true;
      await tester.pump(const Duration(minutes: 3));
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      expect(find.text('Retained note'), findsOneWidget);
      failed = false;
      live = Episode(
        id: 'stale',
        live: true,
        startedAt: start,
        lastActivityAt: clock.now(),
        stateUpdatedAt: clock.now(),
        bullets: const ['Fresh note'],
      );
      await episodes.refreshLive();
      await tester.pump();
      expect(find.byKey(const Key('episode_notes_unavailable')), findsNothing);
      expect(find.text('Fresh note'), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('a closed episode is immediately explicit and stays reachable from the live page', (tester) async {
      final capture = _LiveCapture()..startedAt = _now.subtract(const Duration(minutes: 10));
      Episode? live = _liveEpisode();
      final closed = _liveEpisode().copyWith(live: false);
      final episodes = EpisodeProvider(
        clock: () => _now,
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)),
        lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: closed)),
      )..debugSetLive(live);
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      live = closed;
      await episodes.refreshLive();
      await tester.pump();
      expect(episodes.live, isNull);
      expect(find.byKey(const Key('episode_notes_unavailable')), findsOneWidget);
      expect(find.text('Continues “Lunch plans with Maya”'), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Capturing · 10m 0s');
      await tester.tap(find.text('Continues “Lunch plans with Maya”'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(find.byKey(const Key('previous_episode_page')), findsOneWidget);
      expect(find.text('Lunch plans with Maya'), findsOneWidget);
      expect(find.text('Picking a place near the office'), findsOneWidget);
      expect(find.byKey(const ValueKey('previous_episode_conversation_c1')), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('lazy transcript keeps its frame when the live segment list shrinks', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [for (var i = 0; i < 80; i++) _segment('s$i', 'Synthetic live line $i', i * 20.0)];
      final episodes = _episodes(live: _liveEpisode(items: []));
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
        capture: capture,
        episodes: episodes,
      );
      await tester.pump(const Duration(seconds: 1));
      final list = find.descendant(of: find.byType(TranscriptWidget), matching: find.byType(Scrollable)).first;
      final scroll = tester.state<ScrollableState>(list).position;
      final delegate = tester
          .widget<ListView>(
            find.descendant(of: find.byType(TranscriptWidget), matching: find.byType(ListView)).first,
          )
          .childrenDelegate as SliverChildBuilderDelegate;
      // A server deletion/rollover changes the provider's mutable list before
      // the parent supplies the next frame. The old lazy delegate still exists.
      capture.segments.removeRange(2, capture.segments.length);
      expect(() => delegate.build(tester.element(list), 70), returnsNormally);
      scroll.jumpTo(0);
      await tester.pump();
      expect(tester.takeException(), isNull);
      await _unmount(tester);
    });
    testWidgets('elapsed label ticks each second without segments or server updates', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      final clock = tester.binding.clock;
      final start = clock.now();
      var reads = 0;
      final episode = Episode(
        id: 'ticking',
        live: true,
        startedAt: start.subtract(const Duration(seconds: 57)),
        lastActivityAt: start,
      );
      final episodes = EpisodeProvider(
        fetchLive: () async {
          reads++;
          return ApiSuccess(EpisodeRead(enabled: true, episode: episode));
        },
        clock: clock.now,
      )..debugSetLive(episode);
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      for (final length in ['57s', '58s', '59s', '1m', '1m 1s']) {
        expect(tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel, 'Live · $length');
        await tester.pump(const Duration(seconds: 1));
      }
      expect(reads, 1, reason: 'display ticks do not poll the server');
      await _unmount(tester);
      await tester.pump(const Duration(seconds: 2));
      expect(tester.takeException(), isNull);
    });
    testWidgets('with episodes on it shows the running notes, captured tasks, moments and Wrap Up Now', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [
        _segment('s1', 'Where should we go for lunch?', 0),
        _segment('s2', 'Book it for Friday.', 70),
      ];
      final dismissed = <String>[];
      final episodes = _episodes(live: _liveEpisode(), dismissed: dismissed);
      addTearDown(episodes.dispose);

      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);

      expect(find.byKey(const Key('live_episode_page')), findsOneWidget);
      expect(find.text('Lunch plans with Maya'), findsOneWidget);
      expect(find.byKey(const Key('live_episode_so_far')), findsOneWidget);
      expect(find.textContaining('Picking a place near the office'), findsOneWidget);
      expect(find.textContaining('Book a table for Friday'), findsOneWidget);
      expect(find.text('Where to eat'), findsOneWidget);
      expect(find.text('Booking'), findsOneWidget);
      expect(find.byKey(const Key('episode_wrap_up_button')), findsOneWidget);
      expect(find.text('Omi wraps this up when you move on'), findsOneWidget);
      expect(find.byKey(const Key('process_now_button')), findsNothing);
      // The episode's model state mentions Maya, but no transcript line is resolved to her: the
      // header names only who the transcript names.
      expect(find.text('You, Maya'), findsNothing);

      // Undo on a captured task hides it and tells the server; a refusal brings it back.
      await tester.tap(find.byKey(const ValueKey('episode_item_dismiss_i1')));
      await tester.pump();
      expect(dismissed, ['i1']);
      await tester.pump(const Duration(seconds: 4));
      expect(find.textContaining('Book a table for Friday'), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('Wrap up with nothing new never pauses the pendant: the episode closes and the clock restarts', (
      tester,
    ) async {
      final capture = _PausableCapture();
      addTearDown(capture.dispose);
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);

      await tester.tap(find.byKey(const Key('episode_wrap_up_button')));
      await tester.pump();
      expect(capture.pauses, 0);
      expect(episodes.live, isNull);
      await _unmount(tester);
    });

    testWidgets('while paused the page leads with one-tap Resume, Wrap up beneath it', (tester) async {
      final capture = _PausableCapture()..paused = true;
      addTearDown(capture.dispose);
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);

      final resume = find.byKey(const Key('episode_resume_button'));
      expect(resume, findsOneWidget);
      expect(find.byKey(const Key('episode_wrap_up_button')), findsOneWidget);
      expect(
        tester.getTopLeft(resume).dy,
        lessThan(tester.getTopLeft(find.byKey(const Key('episode_wrap_up_button'))).dy),
      );
      await tester.tap(resume);
      await tester.pump();
      expect(capture.resumes, 1);
      expect(find.byKey(const Key('episode_resume_button')), findsNothing);
      await _unmount(tester);
    });

    testWidgets('the transcript tab draws moment dividers and the captured item inline', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [
        _segment('s1', 'Where should we go for lunch?', 0),
        _segment('s2', 'Book it for Friday.', 70),
      ];
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);

      await _pump(
        tester,
        const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
        capture: capture,
        episodes: episodes,
      );

      expect(find.textContaining('Where should we go for lunch?', findRichText: true), findsOneWidget);
      expect(find.textContaining('Booking'), findsWidgets);
      expect(find.byKey(const ValueKey('episode_item_i1')), findsOneWidget);
      expect(find.byKey(const ValueKey('episode_item_undo_i1')), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('with the server switched off it is today\'s capture page', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [_segment('s1', 'Hello there.', 0)];
      final episodes = _episodes(live: null, enabled: false);
      addTearDown(episodes.dispose);

      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);

      expect(find.byKey(const Key('live_episode_page')), findsNothing);
      expect(find.byKey(const Key('process_now_button')), findsOneWidget);
      expect(find.byKey(const Key('episode_wrap_up_button')), findsNothing);
      await _unmount(tester);
    });
  });

  group('home live row', () {
    testWidgets('Home keeps the disappeared episode even with no history row and opens its member', (tester) async {
      final capture = _LiveCapture();
      final closed = _liveEpisode().copyWith(live: false);
      Episode? live = _liveEpisode();
      final episodes = EpisodeProvider(
        clock: () => _now,
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)),
        lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: closed)),
      )..debugSetLive(live);
      final opened = <String>[];
      addTearDown(capture.dispose);
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        Scaffold(
          body: Column(
            children: [
              const LiveEpisodeRow(),
              PreviousEpisodeLink(onOpenConversation: opened.add),
            ],
          ),
        ),
        capture: capture,
        episodes: episodes,
      );
      live = null;
      await episodes.refreshLive();
      await tester.pump();
      expect(find.byKey(const Key('previous_episode_pill')), findsOneWidget);
      expect(episodes.previous?.live, isFalse);
      final pill = find.byKey(const Key('previous_episode_pill'));
      final target = find.descendant(of: pill, matching: find.byType(InkWell));
      final visual = find.descendant(of: pill, matching: find.byType(Container)).first;
      final hitRect = tester.getRect(target);
      final visualRect = tester.getRect(visual);
      expect(hitRect.height, greaterThanOrEqualTo(44));
      expect(hitRect.width, greaterThanOrEqualTo(44));
      expect(visualRect.height, lessThan(44), reason: 'the visible pill keeps its small size');
      expect(visualRect.center, hitRect.center);
      // Activate the newly reachable area above the visible pill.
      final tap = Offset(hitRect.center.dx, hitRect.top + 1);
      expect(visualRect.contains(tap), isFalse);
      await tester.tapAt(tap);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await tester.tap(find.byKey(const ValueKey('previous_episode_conversation_c1')));
      expect(opened, ['c1']);
      await _unmount(tester);
    });

    testWidgets('the row shows the same live length the episode page shows', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      final clock = tester.binding.clock;
      final start = clock.now();
      final episodes = _episodes(
        live: Episode(
          id: 'timer',
          live: true,
          startedAt: start.subtract(const Duration(seconds: 59)),
          lastActivityAt: start,
        ),
        clock: clock.now,
      );
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        const Scaffold(body: LiveEpisodeRow()),
        capture: capture,
        episodes: episodes,
      );
      expect(_rowLabel(tester), contains('Live · 59s,'));
      await tester.pump(const Duration(seconds: 1));
      // Seconds stay in what the row says: one session duration, formatted exactly as the
      // live page formats it. The tile shows its whole minutes.
      expect(_rowLabel(tester), contains('Live · 1m,'));
      expect(find.text('1m'), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      expect(_rowLabel(tester), contains('Live · 1m 1s,'));
      await _unmount(tester);
    });

    testWidgets('the row and the open episode page read one duration', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      final clock = tester.binding.clock;
      final start = clock.now();
      final episodes = _episodes(
        live: Episode(
          id: 'timer',
          live: true,
          startedAt: start.subtract(const Duration(minutes: 8, seconds: 24)),
          lastActivityAt: start,
        ),
        clock: clock.now,
      );
      addTearDown(episodes.dispose);
      await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes);
      final page = tester.widget<Text>(find.byKey(const Key('live_episode_status'))).semanticsLabel;
      await _unmount(tester);
      await _pump(tester, const Scaffold(body: LiveEpisodeRow()), capture: capture, episodes: episodes);
      // The same wall-clock session: the row's duration is the page's duration.
      expect(_rowLabel(tester), contains(page!));
      expect(find.text('8m'), findsOneWidget);
      await _unmount(tester);
    });

    testWidgets('a local-preview row reads its newest preview line in the subtitle', (tester) async {
      final engine = FakeLivePreviewEngine();
      final preview = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
      );
      preview.admit(language: 'en');
      final clock = tester.binding.clock;
      var disposed = false;
      await tester.runAsync(() async {
        await pumpEventQueue();
        engine.emit('a0', 'Okay, so the plan for Thursday is to ship the pendant update first.', true);
        engine.emit('a1', 'and if the overnight run looks clean we can', false);
        await pumpEventQueue();
      });
      addTearDown(() {
        if (!disposed) preview.dispose();
      });
      final capture = _LiveCapture()
        ..preview = preview
        ..previewAdmitted = true
        ..startedAt = clock.now().subtract(const Duration(minutes: 8, seconds: 24));
      addTearDown(capture.dispose);
      final episodes = _episodes(live: null, clock: clock.now);
      addTearDown(episodes.dispose);
      await _pump(tester, const Scaffold(body: LiveEpisodeRow()), capture: capture, episodes: episodes);
      // The tile carries the length; line two the newest preview words, trimmed at the start.
      expect(find.text('8m'), findsOneWidget);
      final line = tester.widget<Text>(
          find.descendant(of: find.byKey(const Key('home_live_episode_preview')), matching: find.byType(Text)));
      expect(line.textSpan!.toPlainText(), endsWith('and if the overnight run looks clean we can'));
      expect(line.maxLines, 1);
      expect(_rowLabel(tester), contains('Capturing · 8m 24s,'));
      // The cadence timer lives in runAsync's real zone; dispose it there.
      await tester.runAsync(() async {
        preview.dispose();
        disposed = true;
      });
      await _unmount(tester);
    });

    testWidgets('the row keeps the newest preview words after final lines arrive', (tester) async {
      final engine = FakeLivePreviewEngine();
      final preview = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
      );
      preview.admit(language: 'en');
      final clock = tester.binding.clock;
      var disposed = false;
      await tester.runAsync(() async {
        await pumpEventQueue();
        engine.emit('a0', 'and if the overnight run looks clean we can', false);
        await pumpEventQueue();
      });
      addTearDown(() {
        if (!disposed) preview.dispose();
      });
      final capture = _LiveCapture()
        ..preview = preview
        ..previewAdmitted = true
        ..startedAt = clock.now().subtract(const Duration(minutes: 2));
      // The batch transcript has landed for earlier audio; the preview is still ahead of it.
      capture.segments = [_segment('s1', 'Testing live transcription.', 0)];
      addTearDown(capture.dispose);
      final episodes = _episodes(live: null, clock: clock.now);
      addTearDown(episodes.dispose);
      await _pump(tester, const Scaffold(body: LiveEpisodeRow()), capture: capture, episodes: episodes);
      final line = tester.widget<Text>(
          find.descendant(of: find.byKey(const Key('home_live_episode_preview')), matching: find.byType(Text)));
      expect(line.textSpan!.toPlainText(), endsWith('and if the overnight run looks clean we can'));
      // New words land without waiting for the clock's tick.
      await tester.runAsync(() async {
        engine.emit('a0', 'and if the overnight run looks clean we can ship', false);
        await pumpEventQueue();
      });
      await tester.pump();
      final updated = tester.widget<Text>(
          find.descendant(of: find.byKey(const Key('home_live_episode_preview')), matching: find.byType(Text)));
      expect(updated.textSpan!.toPlainText(), endsWith('we can ship'));
      await tester.runAsync(() async {
        preview.dispose();
        disposed = true;
      });
      await _unmount(tester);
    });

    testWidgets('a preview row with no words yet keeps today\'s subtitle', (tester) async {
      final engine = FakeLivePreviewEngine();
      final preview = LivePreviewController(
        engine: engine,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26,
      );
      addTearDown(preview.dispose);
      preview.admit(language: 'en');
      await tester.runAsync(pumpEventQueue);
      final clock = tester.binding.clock;
      final capture = _LiveCapture()
        ..preview = preview
        ..previewAdmitted = true
        ..startedAt = clock.now().subtract(const Duration(seconds: 29));
      addTearDown(capture.dispose);
      final episodes = _episodes(live: null, clock: clock.now);
      addTearDown(episodes.dispose);
      await _pump(tester, const Scaffold(body: LiveEpisodeRow()), capture: capture, episodes: episodes);
      expect(_rowLabel(tester), contains('Capturing · 29s,'));
      expect(find.byKey(const Key('home_live_episode_preview')), findsNothing);
      await _unmount(tester);
    });
    testWidgets('a pendant lease lapsing mid-stream keeps the running length (no 0s)', (tester) async {
      final clock = tester.binding.clock;
      final capture = _LiveCapture()..startedAt = clock.now().subtract(const Duration(minutes: 3, seconds: 12));
      addTearDown(capture.dispose);
      final episodes = _episodes(live: null, clock: clock.now);
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        const Scaffold(body: LiveEpisodeRow()),
        capture: capture,
        episodes: episodes,
      );
      expect(_rowLabel(tester), contains('Capturing · 3m'));
      // The verified-ingress start reads null between health updates, then re-arms later on reconnect.
      capture.startedAt = null;
      await tester.pump(const Duration(seconds: 1));
      expect(_rowLabel(tester), contains('Capturing · 3m'));
      capture.startedAt = clock.now();
      await tester.pump(const Duration(seconds: 1));
      expect(_rowLabel(tester), contains('Capturing · 3m'));
      await _unmount(tester);
    });

    testWidgets('an unverified pendant waits without claiming Listening or a time', (tester) async {
      final en = lookupAppLocalizations(const Locale('en'));
      final capture = _IngressCapture(verified: false);
      addTearDown(capture.dispose);
      final episodes = _episodes(live: null, clock: tester.binding.clock.now);
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        const Scaffold(body: LiveEpisodeRow()),
        capture: capture,
        episodes: episodes,
      );
      expect(find.text(en.captureConnecting), findsOneWidget);
      expect(find.textContaining('Capturing ·', findRichText: true), findsNothing,
          reason: 'a wait claims neither Listening nor a running time');
      expect(find.byKey(const Key('home_live_episode_reconnect')), findsNothing);
      await _unmount(tester);
    });

    testWidgets('an exhausted pendant recovery warns on the row and its action reconnects', (tester) async {
      final en = lookupAppLocalizations(const Locale('en'));
      final capture = _IngressCapture(actionRequired: true);
      addTearDown(capture.dispose);
      final episodes = _episodes(live: null, clock: tester.binding.clock.now);
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        const Scaffold(body: LiveEpisodeRow()),
        capture: capture,
        episodes: episodes,
      );
      // The failure never says Listening: the warning names the problem as the
      // title and the plain-words sentence sits under it, as the island does.
      expect(find.text(en.captureNoAudioFromPendant), findsOneWidget);
      expect(find.text(en.captureNoAudioDetail), findsOneWidget);
      expect(find.text(en.episodeListeningNow), findsNothing, reason: 'a pendant that owes audio is not Listening now');
      expect(find.text(en.captureConnecting), findsNothing);
      expect(find.textContaining('Capturing ·', findRichText: true), findsNothing);
      expect(find.byIcon(Icons.chevron_right_rounded), findsNothing,
          reason: 'the failure replaces the open affordance with its fix');
      await tester.tap(find.byKey(const Key('home_live_episode_reconnect')));
      await tester.pump();
      expect(capture.reconnects, 1);
      await _unmount(tester);
    });
    testWidgets('unnamed voices are never counted as people, however many diarization ids appear', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [
        _segment('me', 'Hello there', 0),
        for (var i = 0; i < 40; i++)
          TranscriptSegment(
            id: 'v$i',
            text: 'Voice $i',
            speaker: 'SPEAKER_${i + 1}',
            isUser: false,
            personId: null,
            translations: [],
            start: 30.0 + i,
            end: 31.0 + i,
          ),
      ];
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);
      await _pump(
        tester,
        const Scaffold(body: LiveEpisodeRow()),
        capture: capture,
        episodes: episodes,
      );
      expect(find.textContaining('people', findRichText: true), findsNothing);
      await _unmount(tester);
    });

    testWidgets('shows the live episode as a quiet outlined row: its topic as title, Live and length', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);

      await _pump(
        tester,
        const Scaffold(body: LiveEpisodeRow()),
        capture: capture,
        episodes: episodes,
      );

      expect(find.byKey(const Key('home_live_episode_row')), findsOneWidget);
      expect(find.text('Lunch plans with Maya'), findsOneWidget);
      expect(find.textContaining('24m', findRichText: true), findsOneWidget);
      // A titled episode's title is its topic; the moment headings would repeat it.
      expect(find.textContaining('Where to eat', findRichText: true), findsNothing);
      // No filled green tile and no dot: the tile holds the running length alone.
      expect(find.byType(OmiBreathingDot), findsNothing);
      expect(find.byType(OmiLiveDot), findsNothing);
      await _unmount(tester);
    });

    testWidgets('the ticking elapsed time never re-announces the row, only a real state change does', (tester) async {
      final capture = _PausableCapture();
      addTearDown(capture.dispose);
      final clock = tester.binding.clock;
      final start = clock.now();
      final episodes = _episodes(
        live: Episode(
            id: 'announce', live: true, startedAt: start.subtract(const Duration(seconds: 10)), lastActivityAt: start),
        clock: clock.now,
      );
      addTearDown(episodes.dispose);
      final announcements = <String>[];
      tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<Object?>(SystemChannels.accessibility,
          (message) async {
        final data = (message as Map)['data'] as Map?;
        final text = data?['message'] as String?;
        if (text != null) announcements.add(text);
        return null;
      });
      addTearDown(() => tester.binding.defaultBinaryMessenger
          .setMockDecodedMessageHandler<Object?>(SystemChannels.accessibility, null));

      await _pump(tester, const Scaffold(body: LiveEpisodeRow()), capture: capture, episodes: episodes);
      final handle = tester.ensureSemantics();

      // The row's own semantics node must not be a live region: previously it wrapped the whole
      // "$title, $rest" label (which includes the ticking elapsed time) in `liveRegion: true`, so
      // assistive tech re-announced the entire row every second it was live.
      expect(
        tester
            .getSemantics(find.byKey(const Key('home_live_episode_row')))
            .getSemanticsData()
            .flagsCollection
            .isLiveRegion,
        isFalse,
      );

      // Several ticks go by with the capture still listening: no announcement fires.
      for (var i = 0; i < 5; i++) {
        await tester.pump(const Duration(seconds: 1));
      }
      expect(announcements, isEmpty);

      // A real state change (paused) still gets announced exactly once.
      capture.paused = true;
      capture.notifyListeners();
      await tester.pump();
      expect(announcements, hasLength(1));

      // Further ticks in the new (paused) state don't repeat the announcement.
      for (var i = 0; i < 3; i++) {
        await tester.pump(const Duration(seconds: 1));
      }
      expect(announcements, hasLength(1));

      handle.dispose();
      await _unmount(tester);
    });
  });

  group('finished episode moments', () {
    Episode closed(int moments) => Episode(
          id: 'ep2',
          live: false,
          startedAt: _now,
          lastActivityAt: _now,
          title: 'Team sync',
          moments: [
            for (var i = 0; i < moments; i++)
              EpisodeMoment(
                id: 'm$i',
                conversationId: i == 0 ? 'c1' : 'c$i',
                startedAt: _now.add(Duration(minutes: 10 * i)),
                endedAt: _now.add(Duration(minutes: 10 * i + 8)),
                heading: 'Part $i',
              ),
          ],
        );

    testWidgets('collapsed by default, expands, and opens a moment from another conversation', (tester) async {
      final opened = <String>[];
      var expanded = false;
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: StatefulBuilder(
              builder: (context, setState) => EpisodeMomentsList(
                episode: closed(3),
                conversationId: 'c1',
                expanded: expanded,
                onToggle: () => setState(() => expanded = !expanded),
                onOpenConversation: opened.add,
              ),
            ),
          ),
        ),
      );
      expect(find.textContaining('3 moments'), findsOneWidget);
      expect(find.text('Part 1'), findsNothing);
      await tester.tap(find.byKey(const Key('episode_moments_toggle')));
      await tester.pump();
      expect(find.text('Part 0'), findsOneWidget);
      expect(find.byKey(const ValueKey('episode_moment_m0')), findsNothing, reason: 'this conversation');
      await tester.tap(find.byKey(const ValueKey('episode_moment_m2')));
      expect(opened, ['c2']);
    });

    testWidgets('a one-moment episode adds nothing to the conversation page', (tester) async {
      final episodes = _episodes(live: null)..debugSetLive(null, byConversation: {'c1': closed(1)});
      addTearDown(episodes.dispose);
      await tester.pumpWidget(
        ChangeNotifierProvider<EpisodeProvider>.value(
          value: episodes,
          child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: EpisodeMomentsSection(conversationId: 'c1')),
          ),
        ),
      );
      await tester.pump();
      expect(find.byKey(const Key('episode_moments_section')), findsNothing);
    });
  });

  group('device page sections', () {
    Widget wrap(Widget child) => MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: ListView(children: [child])),
        );

    testWidgets('stats leave out a battery the device has not reported', (tester) async {
      await tester.pumpWidget(
        wrap(
          const DeviceStatsRow(batteryLevel: 0, isCharging: false, heardTodaySeconds: 3 * 3600, onDeviceSeconds: 600),
        ),
      );
      expect(find.byKey(const Key('device_stat_battery')), findsNothing);
      expect(find.byKey(const Key('device_stat_heard_today')), findsOneWidget);
      expect(find.text('to sync'), findsOneWidget);

      await tester.pumpWidget(
        wrap(const DeviceStatsRow(batteryLevel: 72, isCharging: true, heardTodaySeconds: 0, onDeviceSeconds: 0)),
      );
      expect(find.text('72%'), findsOneWidget);
      expect(find.text('to sync'), findsNothing);
    });

    testWidgets('right now shows the live episode and catching-up progress', (tester) async {
      var opened = 0;
      await tester.pumpWidget(
        wrap(
          DeviceRightNowGroup(
            liveTitle: 'Lunch plans with Maya',
            liveLength: '24m',
            onOpenLive: () => opened++,
            catchingUp: const DeviceCatchUpSummary(status: 'Waiting to sync'),
          ),
        ),
      );
      expect(find.text('Live episode · 24m'), findsOneWidget);
      expect(find.text('Waiting to sync'), findsOneWidget);
      await tester.tap(find.byKey(const Key('device_right_now_live')));
      expect(opened, 1);
    });

    testWidgets('right now waits without a length while the pendant is still verified', (tester) async {
      final en = lookupAppLocalizations(const Locale('en'));
      await tester.pumpWidget(
        wrap(const DeviceRightNowGroup(liveTitle: 'Listening now', liveSubtitle: 'Connecting…')),
      );
      expect(find.text(en.deviceRightNow), findsOneWidget);
      expect(find.text('Connecting…'), findsOneWidget);
      expect(find.byKey(const Key('device_right_now_no_audio')), findsNothing);
    });

    testWidgets('right now names a pendant that owes audio and its tap reconnects', (tester) async {
      final en = lookupAppLocalizations(const Locale('en'));
      var reconnected = 0;
      await tester.pumpWidget(
        wrap(
          DeviceRightNowGroup(
            liveTitle: en.captureNoAudioFromPendant,
            liveSubtitle: en.captureNoAudioDetail,
            liveProblem: true,
            onFixProblem: () => reconnected++,
          ),
        ),
      );
      expect(find.byKey(const Key('device_right_now_no_audio')), findsOneWidget);
      expect(find.text(en.captureNoAudioDetail), findsOneWidget);
      expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
      expect(find.byKey(const Key('device_right_now_live')), findsNothing, reason: 'the failure replaces the live row');
      await tester.tap(find.byKey(const Key('device_right_now_no_audio')));
      expect(reconnected, 1);
    });

    testWidgets('recently lists only real drops from the last day', (tester) async {
      BleDisconnectEvent event(
        DateTime at, {
        int reconnectMs = 90000,
        bool manual = false,
        String type = 'disconnect',
      }) =>
          BleDisconnectEvent(
            timestamp: at.millisecondsSinceEpoch,
            reason: 'link_lost',
            reasonCode: 8,
            eventType: type,
            isManual: manual,
            lastRssi: -70,
            connectionDurationMs: 600000,
            appState: 'foreground',
            timeToReconnectMs: reconnectMs,
            rssiTrend: 'stable',
          );
      await tester.pumpWidget(
        wrap(
          DeviceRecentlyGroup(
            now: () => _now,
            load: () async => [
              event(_now.subtract(const Duration(hours: 30))),
              event(_now.subtract(const Duration(hours: 2)), manual: true),
              event(_now.subtract(const Duration(hours: 1)), type: 'fail_to_connect'),
              event(_now.subtract(const Duration(minutes: 40)), reconnectMs: 0),
              event(_now.subtract(const Duration(minutes: 20))),
            ],
          ),
        ),
      );
      await tester.pump();
      expect(find.byKey(const Key('device_recently')), findsOneWidget);
      expect(find.textContaining('Disconnected for'), findsOneWidget);
    });

    testWidgets('recently is absent with no history', (tester) async {
      await tester.pumpWidget(wrap(DeviceRecentlyGroup(load: () async => const [])));
      await tester.pump();
      expect(find.byKey(const Key('device_recently')), findsNothing);
    });
  });

  testWidgets('a conversation offline sync is filling says so on its own row', (tester) async {
    final conversation = ServerConversation(
      id: 'c1',
      createdAt: DateTime(2026, 10, 20, 9),
      structured: Structured('Morning walk', 'Overview'),
    );
    final provider = ConversationProvider(isSignedIn: () => false)..conversations = [conversation];
    addTearDown(provider.dispose);
    await tester.pumpWidget(
      ChangeNotifierProvider<ConversationProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: ConversationListItem(
              conversation: conversation,
              date: conversation.createdAt,
              conversationIdx: 0,
              fillingSeconds: 720,
            ),
          ),
        ),
      ),
    );
    expect(find.byKey(const Key('conversation_row_filling')), findsOneWidget);
    expect(find.textContaining('from your Omi'), findsOneWidget);
  });
}

/// What the Home live row says: its title, the page's session length, then line two.
String _rowLabel(WidgetTester tester) =>
    tester.widget<Semantics>(find.byKey(const Key('home_live_episode_semantics'))).properties.label ?? '';
