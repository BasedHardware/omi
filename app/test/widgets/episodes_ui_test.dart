import 'package:flutter/material.dart';
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
import 'package:omi/pages/settings/device/device_live_sections.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

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
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  @override
  String? get liveCaptureSource => 'omi';

  @override
  String? get topConversationId => 'c1';
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

EpisodeProvider _episodes({Episode? live, bool enabled = true, List<String>? dismissed}) {
  final provider = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: enabled, episode: live)),
    lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async {
      dismissed?.add(itemId);
      return const ApiFailure(ApiProblem(ApiProblemKind.transport));
    },
    clock: () => _now,
  );
  provider.debugSetLive(live, enabled: enabled);
  return provider;
}

Future<void> _pump(WidgetTester tester, Widget home,
    {required CaptureProvider capture, EpisodeProvider? episodes}) async {
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
            create: (_) => PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []))),
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
    testWidgets('with episodes on it shows the running notes, captured tasks, moments and Wrap Up Now', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [
        _segment('s1', 'Where should we go for lunch?', 0),
        _segment('s2', 'Book it for Friday.', 70)
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

    testWidgets('the transcript tab draws moment dividers and the captured item inline', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      capture.segments = [
        _segment('s1', 'Where should we go for lunch?', 0),
        _segment('s2', 'Book it for Friday.', 70)
      ];
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);

      await _pump(tester, const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
          capture: capture, episodes: episodes);

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
    testWidgets('shows the live episode as a normal row: title, Now, length and topics', (tester) async {
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      final episodes = _episodes(live: _liveEpisode());
      addTearDown(episodes.dispose);

      await _pump(tester, const Scaffold(body: LiveEpisodeRow()), capture: capture, episodes: episodes);

      expect(find.byKey(const Key('home_live_episode_row')), findsOneWidget);
      expect(find.text('Lunch plans with Maya'), findsOneWidget);
      expect(find.textContaining('24m', findRichText: true), findsOneWidget);
      expect(find.textContaining('Where to eat', findRichText: true), findsOneWidget);
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
      await tester.pumpWidget(MaterialApp(
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
      ));
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
      await tester.pumpWidget(ChangeNotifierProvider<EpisodeProvider>.value(
        value: episodes,
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: EpisodeMomentsSection(conversationId: 'c1')),
        ),
      ));
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
      await tester.pumpWidget(wrap(const DeviceStatsRow(
        batteryLevel: 0,
        isCharging: false,
        heardTodaySeconds: 3 * 3600,
        onDeviceSeconds: 600,
      )));
      expect(find.byKey(const Key('device_stat_battery')), findsNothing);
      expect(find.byKey(const Key('device_stat_heard_today')), findsOneWidget);
      expect(find.text('to sync'), findsOneWidget);

      await tester.pumpWidget(wrap(const DeviceStatsRow(
        batteryLevel: 72,
        isCharging: true,
        heardTodaySeconds: 0,
        onDeviceSeconds: 0,
      )));
      expect(find.text('72%'), findsOneWidget);
      expect(find.text('to sync'), findsNothing);
    });

    testWidgets('right now shows the live episode and catching-up progress', (tester) async {
      var opened = 0;
      await tester.pumpWidget(wrap(DeviceRightNowGroup(
        liveTitle: 'Lunch plans with Maya',
        liveLength: '24m',
        onOpenLive: () => opened++,
        catchingUp: (doneSeconds: 240, totalSeconds: 720),
      )));
      expect(find.text('Live episode · 24m'), findsOneWidget);
      expect(find.text('4 of 12 min'), findsOneWidget);
      await tester.tap(find.byKey(const Key('device_right_now_live')));
      expect(opened, 1);
    });

    testWidgets('recently lists only real drops from the last day', (tester) async {
      BleDisconnectEvent event(DateTime at,
              {int reconnectMs = 90000, bool manual = false, String type = 'disconnect'}) =>
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
      await tester.pumpWidget(wrap(DeviceRecentlyGroup(
        now: () => _now,
        load: () async => [
          event(_now.subtract(const Duration(hours: 30))),
          event(_now.subtract(const Duration(hours: 2)), manual: true),
          event(_now.subtract(const Duration(hours: 1)), type: 'fail_to_connect'),
          event(_now.subtract(const Duration(minutes: 40)), reconnectMs: 0),
          event(_now.subtract(const Duration(minutes: 20))),
        ],
      )));
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
    await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(
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
    ));
    expect(find.byKey(const Key('conversation_row_filling')), findsOneWidget);
    expect(find.textContaining('from your Omi'), findsOneWidget);
  });
}
