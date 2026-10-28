import 'dart:collection';
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
import 'package:omi/env/env.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
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
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart' show Wal;
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Hermetic fixture adapted from home_after_detail_perf_test.dart. Its list is
// larger and its sync is active; counters isolate the remaining page scan.

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
  double _progress = 0.25;
  void ping() {
    _progress += 0.01;
    notifyListeners();
  }

  @override
  SyncState get syncState =>
      SyncState(status: SyncStatus.syncing, phase: SyncPhase.uploadingToCloud, progress: _progress);

  @override
  bool get isSyncing => true;

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
  void ping() => notifyListeners();
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
/// row), 300 conversations as the list endpoint projects them (two lines each),
/// and an active background sync. All providers are local fakes or hermetic.
class _Home {
  _Home({this.background = const {}});

  /// Conversations whose notes call them background (Episodes M3).
  final Set<int> background;
  DateTime now = _seedNow;
  final sync = _StubSyncProvider();
  late final _LiveCapture capture = _LiveCapture();
  late final EpisodeProvider episodes = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _liveEpisode())),
    lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    clock: () => now,
  );
  late final _Conversations conversations = _Conversations()
    ..conversations = [
      for (var i = 0; i < 300; i++)
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
      ChangeNotifierProvider<SyncProvider>.value(value: home.sync),
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

class _Conversations extends ConversationProvider {
  _Conversations() : super(isSignedIn: () => false);
  void ping() => notifyListeners();
}

class _History extends ListBase<ServerConversation> {
  _History(this.rows);
  final List<ServerConversation> rows;
  int signatureEvaluations = 0;
  int signatureReads = 0;
  @override
  int get length => rows.length;
  @override
  set length(int value) => rows.length = value;
  @override
  ServerConversation operator [](int i) => rows[i];
  @override
  void operator []=(int i, ServerConversation value) => rows[i] = value;
  @override
  Iterable<T> map<T>(T Function(ServerConversation) convert) sync* {
    for (final row in this) {
      yield convert(row);
    }
  }

  @override
  Iterator<ServerConversation> get iterator {
    // Attribution is test-only and runs once per traversal, never per row.
    final signature = StackTrace.current.toString().contains('_identitySignature');
    if (signature) signatureEvaluations++;
    return _Iterator(rows.iterator, signature ? () => signatureReads++ : () {});
  }
}

class _Iterator implements Iterator<ServerConversation> {
  _Iterator(this.inner, this.onRead);
  final Iterator<ServerConversation> inner;
  final VoidCallback onRead;
  @override
  ServerConversation get current => inner.current;
  @override
  bool moveNext() {
    final hasNext = inner.moveNext();
    if (hasNext) onRead();
    return hasNext;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    AnalyticsManager.configure(_RecordingAdapter());
    await AnalyticsManager.init();
  });
  tearDown(() {
    debugOnRebuildDirtyWidget = null;
    Env.clearApiBaseUrlOverrideForTesting();
    AnalyticsManager.resetForTesting();
    VisibilityDetectorController.instance.updateInterval = const Duration(milliseconds: 500);
  });
  testWidgets('handoff: 300-row Home capture and sync fling census', (tester) async {
    final home = await _pumpHome(tester);
    // This is an already-active capture. Avoid first-line metadata/location
    // bootstrap; the census exercises subsequent production segment arrivals.
    home.capture.segments = [_segment(0)];
    final history = _History(home.conversations.conversations);
    home.conversations.conversations = history;
    home.conversations.ping();
    await tester.pump();
    history.signatureEvaluations = 0;
    history.signatureReads = 0;
    final builds = <String, int>{};
    debugOnRebuildDirtyWidget = (element, _) {
      final key = element.widget.runtimeType.toString();
      builds[key] = (builds[key] ?? 0) + 1;
    };
    var callbacks = 0;
    var captureNotifies = 0;
    var syncNotifies = 0;
    var historyNotifies = 0;
    home.capture.addListener(() => captureNotifies++);
    home.sync.addListener(() => syncNotifies++);
    home.conversations.addListener(() => historyNotifies++);
    await tester.fling(find.byType(CustomScrollView).first, const Offset(0, -1800), 3000);
    for (var frame = 0; frame < 30; frame++) {
      if (frame % 3 == 0) {
        home.capture.onSegmentReceived([_segment(2000 + frame)]);
        home.sync.ping();
      }
      if (frame % 6 == 0) home.conversations.ping();
      await tester.pump(const Duration(milliseconds: 16));
      callbacks += SchedulerBinding.instance.transientCallbackCount;
    }
    debugPrint(
        'SCROLL_HOME rows=300 frames=30 capture_notifies=$captureNotifies sync_notifies=$syncNotifies history_notifies=$historyNotifies '
        'signature_evaluations=${history.signatureEvaluations} signature_row_reads=${history.signatureReads} '
        'page_builds=${builds['ConversationsPage'] ?? 0} row_builds=${builds['ConversationListItem'] ?? 0} '
        'transient_callbacks=$callbacks');
    // This is an attributed measurement of off-limits page work, not a claim
    // that an unchanged selector result is free. Route its fix to the lead.
    expect(history.signatureEvaluations, greaterThanOrEqualTo(5));
    expect(history.signatureReads, history.signatureEvaluations * 300);
    debugOnRebuildDirtyWidget = null;
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
    home.capture.dispose();
    home.conversations.dispose();
    home.episodes.dispose();
    home.sync.dispose();
  });
}
