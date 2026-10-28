import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart' show ConversationDetailPage;
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart' show Wal;
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Home scroll guards around a conversation detail visit (P36).
///
/// Home with a live capture can animate continuously, so
/// `transientCallbackCount` never reaches zero there. Opening a row must not
/// hand the scheduler an idle-priority task: `SchedulerBinding._runTasks`
/// re-arms a zero-delay timer every event-loop turn while an animation keeps
/// an idle task from running, which spins the UI isolate until the animation
/// stops. The other guards keep the 1-second tick inside its leaf, a detail
/// visit free of leftover tickers and timers, and list updates to one shell
/// build per visible row.

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  BtDevice? get pairedDevice => null;

  @override
  bool get isConnected => false;

  @override
  bool get isConnecting => false;

  @override
  bool get havingNewFirmware => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubPhoneCallProvider extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubSyncProvider extends ChangeNotifier implements SyncProvider {
  @override
  SyncState get syncState => const SyncState();

  @override
  bool get isSyncing => false;

  @override
  List<Wal> get allWals => const [];

  @override
  List<Wal> get uploadedWals => const [];

  @override
  List<Wal> get displaySortedWals => const [];

  @override
  bool get isRateLimited => false;

  @override
  ({int doneSeconds, int totalSeconds, bool tracked}) get offlineServerProcessingSeconds =>
      (doneSeconds: 0, totalSeconds: 0, tracked: false);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubLocalRecordings extends ChangeNotifier implements LocalRecordingsProvider {
  @override
  List<LocalRecording> get recordings => const [];

  @override
  Future<void> refresh() async {}

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

class _Syncs {
  final phone = _PhoneSync();
}

class _WalService implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
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
  String? get topConversationId => 'conv-0-live';
}

class _RecordingAdapter implements AnalyticsAdapter {
  final events = <String>[];
  bool initialized = false;

  @override
  bool get isInitialized => initialized;

  @override
  Future<void> init() async => initialized = true;

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add(eventName);

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}

final _seedNow = DateTime(2026, 10, 21, 12, 30);

TranscriptSegment _segment(int i) => TranscriptSegment(
      id: 'seg-$i',
      text: 'Line $i of a long conversation about rollout lanes and capacity.',
      speaker: 'SPEAKER_0',
      isUser: true,
      personId: null,
      translations: [],
      start: i * 8.0,
      end: i * 8.0 + 7,
    );

ServerConversation _conversation(int i, {int segmentCount = 0, String? salience}) {
  final created = _seedNow.subtract(Duration(hours: 3 * i));
  return ServerConversation(
    id: 'conv-$i',
    speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0]),
    createdAt: created,
    startedAt: created,
    finishedAt: created.add(const Duration(minutes: 22)),
    structured: Structured('Conversation $i', 'Overview $i.', emoji: '🧠', category: 'other', salience: salience),
    transcriptSegments: [for (var j = 0; j < segmentCount; j++) _segment(j)..isUser = salience != 'background'],
  );
}

Episode _liveEpisode() => Episode(
      id: 'ep1',
      live: true,
      startedAt: _seedNow.subtract(const Duration(minutes: 24)),
      lastActivityAt: _seedNow,
      title: 'Live capture',
      bullets: const [],
      people: const [],
      items: const [],
      moments: const [],
      conversationIds: const [],
      stateUpdatedAt: _seedNow,
    );

/// Home as David sees it: a pendant streaming into a live episode (the live
/// row), 30 conversations as the list endpoint projects them (two lines each),
/// and the detail endpoint hydrating an opened one with its full transcript.
class _Home {
  _Home({this.background = const {}});

  /// Conversations whose notes call them background (Episodes M3).
  final Set<int> background;
  DateTime now = _seedNow;
  late final _LiveCapture capture = _LiveCapture();
  late final EpisodeProvider episodes = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _liveEpisode())),
    lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    clock: () => now,
  );
  late final ConversationProvider conversations = ConversationProvider(isSignedIn: () => false)
    ..conversations = [
      for (var i = 0; i < 30; i++)
        _conversation(i, segmentCount: 2, salience: background.contains(i) ? 'background' : null),
    ]
    ..groupConversationsByDate()
    ..conversationDetailsFetcherOverride = (id) async => hydrated(int.parse(id.substring('conv-'.length)));

  /// The detail endpoint's copy: the same conversation with every line.
  ServerConversation hydrated(int i, {int segmentCount = 1500}) => _conversation(i, segmentCount: segmentCount);
}

Widget _app(_Home home) {
  // Providers wrap the MaterialApp, as lib/main.dart does, so a pushed detail
  // route resolves them too; the detail provider keeps its production proxy.
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<ConversationProvider>.value(value: home.conversations),
      ChangeNotifierProvider<AppProvider>.value(value: AppProvider()),
      ChangeNotifierProvider<CaptureProvider>.value(value: home.capture),
      ChangeNotifierProvider<EpisodeProvider>.value(value: home.episodes),
      ChangeNotifierProvider<LocalRecordingsProvider>.value(value: _StubLocalRecordings()),
      ChangeNotifierProvider<FolderProvider>.value(value: FolderProvider(foldersFetcher: () async => <Folder>[])),
      ChangeNotifierProvider<HomeProvider>.value(value: HomeProvider()),
      ChangeNotifierProvider<DeviceProvider>.value(value: _StubDeviceProvider()),
      ChangeNotifierProvider<PhoneCallProvider>.value(value: _StubPhoneCallProvider()),
      ChangeNotifierProvider<SpeakerTagPromptsProvider>.value(
        value: SpeakerTagPromptsProvider(
          fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()),
        ),
      ),
      ChangeNotifierProvider<SyncProvider>.value(value: _StubSyncProvider()),
      ChangeNotifierProvider<ConnectivityProvider>.value(value: _StubConnectivityProvider()),
      ChangeNotifierProvider<PeopleProvider>.value(
        value: PeopleProvider(loadPeople: () async => const PeopleListResponse(people: [])),
      ),
      ChangeNotifierProvider<UsageProvider>.value(value: UsageProvider()),
      ChangeNotifierProvider<IntegrationProvider>.value(
        value: IntegrationProvider(
          fetchStatus: (_) async => null,
          saveStatus: (_, __) async => false,
          deleteStatus: (_) async => false,
          persistPref: (_, __) async {},
        ),
      ),
      ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
        create: (_) => ConversationDetailProvider(),
        update: (_, app, conversations, previous) =>
            (previous?..setProviders(app, conversations)) ?? ConversationDetailProvider(),
      ),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(
        // Home's live row no longer pulses (David, 10-27: no dot in the tile). A breathing dot
        // stands in for any running Home animation, so the scheduler guards run as on device
        // while something animates.
        floatingActionButton: const OmiBreathingDot(live: true),
        body: ConversationsPage(
          requestInitialLoad: false,
          loadRecaps: () async => (items: <DailySummary>[], ok: true),
          pendingWork: PendingWorkStore(
            loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
            loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
          ),
        ),
      ),
    ),
  );
}

Future<_Home> _pumpHome(WidgetTester tester, {Set<int> background = const {}}) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final home = _Home(background: background);
  await tester.pumpWidget(_app(home));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
  expect(find.byType(LiveEpisodeRow), findsOneWidget, reason: 'Home must show the live episode row');
  expect(find.byType(ConversationListItem), findsWidgets);
  expect(tester.binding.transientCallbackCount, greaterThan(0), reason: 'Home must be animating');
  return home;
}

/// Rebuilds by widget type while [body] runs.
Future<Map<String, int>> _rebuildsDuring(Future<void> Function() body) async {
  final builds = <String, int>{};
  final previous = debugOnRebuildDirtyWidget;
  debugOnRebuildDirtyWidget = (element, builtOnce) {
    builds.update(element.widget.runtimeType.toString(), (n) => n + 1, ifAbsent: () => 1);
    previous?.call(element, builtOnce);
  };
  try {
    await body();
  } finally {
    debugOnRebuildDirtyWidget = previous;
  }
  return builds;
}

Future<void> _tickSeconds(WidgetTester tester, int seconds) async {
  for (var i = 0; i < seconds; i++) {
    await tester.pump(const Duration(seconds: 1));
  }
}

Future<void> _openAndCloseRow(WidgetTester tester, String conversationId) async {
  await tester.tap(find.byKey(ValueKey(conversationId)));
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 400));
  }
  expect(find.byType(ConversationDetailPage), findsOneWidget);
  Navigator.of(tester.element(find.byType(ConversationDetailPage))).pop();
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
  expect(find.byType(ConversationDetailPage), findsNothing);
}

/// Fires every short timer the page leaves after a scroll or a list update,
/// before and after the tree goes away, so the binding's pending-timer check
/// sees none.
Future<void> _drainAndUnmount(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 1));
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(seconds: 1));
}

/// Five ticks may rebuild the page shell once (the 30-second episode poll or the midnight rollover
/// can land in the window), never once per tick, and never a conversation row. A shell rebuild
/// also rebuilds the clock's element, so only the shell bound, not the clock count, guards the
/// per-tick amplification.
void _expectTickStaysInLeaf(Map<String, int> rebuilds, {required String when}) {
  expect(rebuilds['LiveEpisodeClock'] ?? 0, greaterThanOrEqualTo(5), reason: '$when: the clock must tick each second');
  expect(rebuilds['ConversationListItem'], isNull, reason: '$when: a tick must not rebuild a conversation row');
  for (final shell in ['ConversationsPage', 'ConversationCaptureWidget']) {
    expect(rebuilds[shell] ?? 0, lessThanOrEqualTo(1), reason: '$when: a tick must not rebuild $shell');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _RecordingAdapter analytics;

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    analytics = _RecordingAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
  });
  tearDown(() {
    AnalyticsManager.resetForTesting();
    VisibilityDetectorController.instance.updateInterval = const Duration(milliseconds: 500);
  });

  testWidgets('a conversation the person just ended shows as a processing row under the live row', (tester) async {
    final home = await _pumpHome(tester);
    home.conversations.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    final row = find.byKey(const Key('home_processing_row'));
    expect(row, findsOneWidget);
    expect(find.descendant(of: row, matching: find.text('Processing…')), findsOneWidget);
    expect(tester.getTopLeft(row).dy, greaterThan(tester.getTopLeft(find.byType(LiveEpisodeRow)).dy));
    expect(tester.getTopLeft(row).dy, lessThan(tester.getTopLeft(find.byKey(const ValueKey('conv-0'))).dy));
    // The server's row replaces it, then the finished conversation takes its own row.
    home.conversations.removeProcessingConversation(OptimisticProcessingPlaceholder.id);
    await tester.pump();
    expect(find.byKey(const Key('home_processing_row')), findsNothing);
    await _drainAndUnmount(tester);
  });

  testWidgets('background conversations leave Home for the daily recap, with no line or toggle', (tester) async {
    // Today holds conv-0 (12:30), conv-1 (09:30), conv-2 (06:30) and conv-3 (03:30).
    await _pumpHome(tester, background: {1, 2});
    expect(find.byKey(const ValueKey('conv-1')), findsNothing);
    expect(find.byKey(const ValueKey('conv-2')), findsNothing);
    expect(find.byKey(const ValueKey('conv-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('conv-3')), findsOneWidget);
    expect(find.textContaining('Also:'), findsNothing);
    await _drainAndUnmount(tester);
  });

  testWidgets('opening a row hands the scheduler no idle task while Home animates, and still reports the open',
      (tester) async {
    await _pumpHome(tester);

    // The spin shape: the strategy is consulted again and again for a task it refuses to run.
    var consultations = 0;
    tester.binding.schedulingStrategy = ({required int priority, required SchedulerBinding scheduler}) {
      if (++consultations > 50) {
        fail('an idle-priority task is spinning the event loop behind a running animation');
      }
      return defaultSchedulingStrategy(priority: priority, scheduler: scheduler);
    };
    addTearDown(() => tester.binding.schedulingStrategy = defaultSchedulingStrategy);

    await _openAndCloseRow(tester, 'conv-3');
    await _tickSeconds(tester, 2);
    expect(consultations, 0, reason: 'opening a conversation must not queue a SchedulerBinding task');

    await AnalyticsManager.flushPending(force: true);
    expect(analytics.events, contains('Conversation List Item Clicked'),
        reason: 'the open must still be reported while Home animates');
    await _drainAndUnmount(tester);
  });

  testWidgets('Home rebuilds stay bounded across detail visits, ticker ticks and list updates', (tester) async {
    final home = await _pumpHome(tester);
    final baselineTickers = tester.binding.transientCallbackCount;

    // The 1-second tick stays inside the live row's clock.
    final tick = await _rebuildsDuring(() async {
      home.now = home.now.add(const Duration(seconds: 5));
      await _tickSeconds(tester, 5);
    });
    debugPrint('TICK rebuilds: $tick');
    _expectTickStaysInLeaf(tick, when: 'idle');

    // Three detail visits of a hydrated conversation leave no ticker or rebuild behind.
    for (var visit = 0; visit < 3; visit++) {
      await _openAndCloseRow(tester, 'conv-3');
    }
    expect(tester.binding.transientCallbackCount, baselineTickers, reason: 'a detail visit must not leak a ticker');
    final afterVisits = await _rebuildsDuring(() => _tickSeconds(tester, 5));
    debugPrint('AFTER VISITS tick rebuilds: $afterVisits');
    _expectTickStaysInLeaf(afterVisits, when: 'after a visit');

    // Ten completions landing (identity replacements) cost at most one row shell per mounted row each
    // (the sliver keeps rows mounted past the viewport, so count offstage ones too).
    int mountedRows() => find.byType(ConversationListItem, skipOffstage: false).evaluate().length;
    var maxMounted = mountedRows();
    const updates = 10;
    final listUpdates = await _rebuildsDuring(() async {
      for (var i = 10; i < 10 + updates; i++) {
        home.conversations.updateConversationInSortedList(home.hydrated(i, segmentCount: 1200));
        await tester.pump(const Duration(milliseconds: 200));
        if (mountedRows() > maxMounted) maxMounted = mountedRows();
      }
    });
    debugPrint('LIST UPDATES mounted<=$maxMounted rows=${listUpdates['ConversationListItem']} '
        'swipeRows=${listUpdates['_SwipeDeleteRow']}');
    expect(listUpdates['ConversationsPage'], isNull, reason: 'a list update must not rebuild the page shell');
    expect(listUpdates['ConversationListItem'] ?? 0, lessThanOrEqualTo(updates * maxMounted),
        reason: 'a list update must cost at most one shell build per mounted row');

    // Two flings: rows build as they enter the viewport, not every frame.
    final uiMs = <double>[];
    final scroll = await _rebuildsDuring(() async {
      for (var i = 0; i < 2; i++) {
        await tester.fling(find.byType(CustomScrollView).first, const Offset(0, -700), 2500);
        for (var f = 0; f < 30; f++) {
          tester.binding.scheduleFrameCallback((_) {
            final watch = Stopwatch()..start();
            tester.binding.addPostFrameCallback((_) => uiMs.add(watch.elapsedMicroseconds / 1000));
          });
          await tester.pump(const Duration(microseconds: 16667));
        }
      }
    });
    final sorted = [...uiMs]..sort();
    debugPrint(
        'SCROLL frames=${uiMs.length} hostUiMs p50=${sorted[(sorted.length * .5).ceil() - 1].toStringAsFixed(3)} '
        'p95=${sorted[(sorted.length * .95).ceil() - 1].toStringAsFixed(3)} rows=${scroll['ConversationListItem']}');
    expect(scroll['ConversationListItem'] ?? 0, lessThanOrEqualTo(home.conversations.conversations.length),
        reason: 'scrolling must build a row once as it enters the viewport, not per frame');
    expect(scroll['ConversationsPage'], isNull);

    expect(tester.takeException(), isNull);
    await _drainAndUnmount(tester);
  });
}
