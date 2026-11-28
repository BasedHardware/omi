import 'dart:async';
import 'dart:ui' show SemanticsAction;

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
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/episodes/episode_moments_section.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/previous_episode_link.dart';
import 'package:omi/pages/settings/device/device_live_sections.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/utils/enums.dart';

import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
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

  DateTime? transcriptOrigin;

  @override
  DateTime? get liveTranscriptStartedAt => transcriptOrigin ?? super.liveTranscriptStartedAt;

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
          .widget<SliverList>(
            find.descendant(of: find.byType(TranscriptWidget), matching: find.byType(SliverList)).first,
          )
          .delegate as SliverChildBuilderDelegate;
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
    testWidgets('with episodes on it shows the running notes, captured tasks and Wrap Up Now', (tester) async {
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
      expect(find.text('Where to eat'), findsNothing);
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
          const DeviceStatsRow(batteryLevel: -1, isCharging: false, heardTodaySeconds: 3 * 3600, onDeviceSeconds: 600),
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

    testWidgets('a reported zero stays visible without a battery action', (tester) async {
      final semantics = tester.ensureSemantics();
      try {
        await tester.pumpWidget(wrap(const DeviceStatsRow(
          batteryLevel: 0,
          isCharging: false,
          heardTodaySeconds: 0,
          onDeviceSeconds: 0,
        )));
        expect(find.text('0%'), findsOneWidget);
        final battery = find.byKey(const Key('device_stat_battery'));
        expect(tester.getSemantics(battery).getSemanticsData().hasAction(SemanticsAction.tap), isFalse);
        expect(find.text('Try Again'), findsNothing);
      } finally {
        semantics.dispose();
      }
    });

    testWidgets('right now shows only the live episode', (tester) async {
      var opened = 0;
      await tester.pumpWidget(
        wrap(
          DeviceRightNowGroup(
            liveTitle: 'Lunch plans with Maya',
            liveLength: '24m',
            onOpenLive: () => opened++,
          ),
        ),
      );
      expect(find.text('Live episode · 24m'), findsOneWidget);
      expect(find.text('Catching up'), findsNothing);
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
  });
}
