import 'package:clock/clock.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
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
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/live_summary_section.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_tab.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversation_detail/widgets.dart' show ConversationTitleField;
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/v3_live_placeholder_row.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/conversations/widgets/day_summary_link.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/episodes/finish_capture.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
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
import 'package:omi/services/capture/finish_outcome.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/conversation_summary_stream.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart' show Wal;
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;

import '../../helpers/sfpro_font_fixtures.dart';

// v3 Home (recordings and conversations), on the hermetic fixture of perf/scroll_home_notify_test.dart.

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
  String? get liveCaptureSource => streaming ? 'omi' : null;

  bool streaming = true;

  @override
  String? activeRecordingId = 'capture-1';
  ServerConversation Function(String?)? onManualEnd;
  void Function(ServerConversation)? onDrainFailed;

  @override
  String? topConversationId = 'conv-0-live';

  bool segmentsFromSocket = true;

  @override
  Iterable<String> get locallyReceivedSegmentIds =>
      segmentsFromSocket ? segments.map((segment) => segment.id) : super.locallyReceivedSegmentIds;

  /// Taps on End: the pendant double-tap's action, without draining a real capture.
  int endCalls = 0;
  String? endedLiveId;

  int finishCalls = 0;
  String? finishedRecordingId;
  String? finishedLiveId;
  String recordingToProcess = 'rec-1';
  final closedRecordingIds = <String>{};

  @override
  bool hasClosedServerRecording(String recordingId) => closedRecordingIds.contains(recordingId);

  @override
  Future<InProgressProcessOutcome> finishCaptureWithOutcome({String? liveConversationId}) async {
    finishCalls++;
    finishedRecordingId = recordingToProcess;
    finishedLiveId = liveConversationId;
    onManualEnd?.call(liveConversationId);
    return InProgressProcessOutcome(
      response: CreateConversationResponse(
        messages: const [],
        conversation: _conversation(
          recordingToProcess,
          _now,
          '',
          v3: const ConversationV3Fields(recording: true, tileState: ConversationTileState.transcribing),
        ),
      ),
    );
  }

  /// Keeps the segments and ownership visible until End's local drain settles.
  Completer<void>? drain;
  // The real controller keeps the verified pendant recording after a successful close.
  bool keepVerifiedAfterClose = false;

  @override
  String? verifiedLiveServerRecordingId;

  @override
  Future<void> forceProcessingCurrentConversation({bool manualFinish = false, String? liveConversationId}) async {
    endCalls++;
    endedLiveId = liveConversationId;
    final row = manualFinish ? onManualEnd?.call(liveConversationId) : null;
    try {
      await drain?.future;
    } catch (_) {
      if (row != null) onDrainFailed?.call(row);
      rethrow;
    }
    segments = [];
    if (!keepVerifiedAfterClose) verifiedLiveServerRecordingId = null;
    notifyListeners();
  }
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

final _now = DateTime(2026, 11, 16, 12, 30);

ServerConversation _conversation(String id, DateTime start, String title,
        {ConversationV3Fields? v3,
        ConversationStatus status = ConversationStatus.completed,
        Duration length = const Duration(minutes: 25),
        DateTime? lastSpeech,
        List<TranscriptSegment> segments = const []}) =>
    ServerConversation(
      id: id,
      status: status,
      speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0]),
      createdAt: start,
      startedAt: start,
      finishedAt: v3?.tileState == ConversationTileState.live ? lastSpeech : start.add(length),
      structured: Structured(title, 'Overview of $title.', emoji: '💬', category: 'work'),
      transcriptSegments: segments,
      v3: v3,
    );

TranscriptSegment _said(String id, String text, double start, double end, {bool user = true}) => TranscriptSegment(
    id: id,
    text: text,
    speaker: user ? 'SPEAKER_00' : 'SPEAKER_01',
    isUser: user,
    personId: null,
    start: start,
    end: end,
    translations: []);

/// What was said so far in the conversation in progress: an 11-minute speech span, the length its
/// Home row and its page both show.
final _liveSoFar = [
  _said('l1', 'Okay, launch checklist. The venue confirmed Thursday the 26th.', 0, 6),
  _said('l2', 'Deposit is due Friday, so I will send it tomorrow morning.', 7, 12, user: false),
  _said('l3', 'Capacity is 180 seated. We need to cut the list by about twenty.', 300, 306),
  _said('l4', 'Priya sends the speaker bios by Tuesday; I own the slide order.', 640, 660, user: false),
];

const _done = ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.done, titleLocked: true);

/// Home for a v3 account: two finished conversations today (one still being written), one hidden
/// from Home, one yesterday, and the conversation in progress from the live read.
class _Home {
  _Home({required this.v3, this.remembered = true});

  final bool v3;

  /// False: the first launch after this build, before the switch has ever answered.
  final bool remembered;
  int episodeCalls = 0;
  int liveReads = 0;

  /// Reads of the open conversation by its detail page, and the state those reads return.
  int detailReads = 0;
  ConversationTileState detailState = ConversationTileState.live;

  List<TranscriptSegment> detailSegments = _liveSoFar;
  Completer<void>? detailBarrier;
  bool detailFails = false;
  bool detailDenied = false;
  bool detailHidden = false;

  Future<({ServerConversation? item, bool ok, bool inaccessible})> detailResult(String id) async {
    final item = await detailRead(id);
    return (item: detailDenied ? null : item, ok: item != null, inaccessible: detailDenied);
  }

  Future<ServerConversation?> detailRead(String id) async {
    detailReads++;
    await detailBarrier?.future;
    if (id != liveId || detailFails) return null;
    return _conversation(id, liveStart, liveTitle,
        lastSpeech: _now.subtract(const Duration(minutes: 9)),
        segments: detailSegments,
        v3: ConversationV3Fields(
            kind: 'conversation', tileState: detailState, homeHidden: detailHidden, recordingIds: liveRecordingIds));
  }

  /// False once the conversation in progress has closed.
  bool liveOpen = true;
  String liveId = 'live-1';

  /// The server's title for the conversation in progress; empty until the server names it.
  String liveTitle = 'Launch checklist';

  /// The live window's start, and whether Home hides it.
  late DateTime liveStart = _now.subtract(const Duration(minutes: 20));
  bool liveHidden = false;
  bool liveFailed = false;
  List<String> liveRecordingIds = const ['rec-1'];
  final sync = _StubSyncProvider();
  late final _LiveCapture capture = _LiveCapture()
    ..segments = [
      // The same segment the open window's transcript ends with: this phone's capture is in it.
      TranscriptSegment(
          id: 'l4',
          text: 'Doors at six.',
          speaker: 'SPEAKER_00',
          isUser: true,
          personId: null,
          start: 0,
          end: 2,
          translations: []),
    ];
  late final EpisodeProvider episodes = EpisodeProvider(
    fetchPage: (from, to, {cursor}) async {
      episodeCalls++;
      return const ApiSuccess(EpisodePageRead(enabled: true));
    },
    fetchLive: () async {
      episodeCalls++;
      return ApiSuccess(EpisodeRead(
        enabled: true,
        episode: Episode(
          id: 'ep1',
          live: true,
          startedAt: _now.subtract(const Duration(minutes: 24)),
          lastActivityAt: _now,
          title: 'Live capture',
          bullets: const [],
          people: const [],
          items: const [],
          moments: const [],
          conversationIds: const [],
          stateUpdatedAt: _now,
        ),
      ));
    },
    lookup: (_) async {
      episodeCalls++;
      return const ApiSuccess(EpisodeRead.disabled);
    },
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    clock: () => _now,
  )..suppressed = () => conversationsV3.v3;
  late final ConversationsV3Provider conversationsV3 = ConversationsV3Provider(
    uid: () => SharedPreferencesUtil().uid,
    // Steady state: the last answer is remembered for this account. (The very first launch after the
    // switch turns on makes one episode read before the first live answer lands.)
    cached: remembered ? 'owner-1:${v3 ? 1 : 0}' : '',
    fetchLive: () async {
      liveReads++;
      return ApiSuccess(
        ConversationsLiveRead(
          v3: v3,
          conversation: v3 && liveOpen
              ? _conversation(
                  liveId, liveStart, liveTitle,
                  // The server's finished_at for an open window is its last speech: 11 minutes in.
                  lastSpeech: _now.subtract(const Duration(minutes: 9)),
                  segments: _liveSoFar,
                  v3: ConversationV3Fields(
                    kind: 'conversation',
                    tileState: liveFailed ? ConversationTileState.failed : ConversationTileState.live,
                    homeHidden: liveHidden,
                    recordingIds: liveRecordingIds,
                  ),
                )
              : null,
        ),
      );
    },
  );
  void publishManualEnds() {
    capture.onManualEnd = (id) {
      final pending = OptimisticProcessingPlaceholder.conversation();
      final sourceId = capture.verifiedLiveServerRecordingId ?? capture.recordingToProcess;
      conversationsV3.startManualFinish(pending, capture.hasClosedServerRecording(sourceId) ? null : sourceId,
          liveConversationId: id, captureId: capture.activeRecordingId);
      return pending;
    };
    capture.onDrainFailed = (row) => conversationsV3.settleManualFinish(row, null);
  }

  late final _Conversations conversations = _Conversations()
    ..conversations = [
      // A phone call that started after the conversation in progress: still sorts below it.
      _conversation('c-call', DateTime(2026, 11, 16, 12, 20), 'Call from the printer', v3: null),
      // The capture socket delivered a recording: never a row.
      _conversation('rec-1', DateTime(2026, 11, 16, 12, 15), 'Recording',
          v3: const ConversationV3Fields(recording: true)),
      _conversation('c-transcribing', DateTime(2026, 11, 16, 11, 20), 'Call with the venue',
          v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.transcribing)),
      _conversation('c-writing', DateTime(2026, 11, 16, 10, 30), 'Hiring plan',
          v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.writing)),
      _conversation('c-hidden', DateTime(2026, 11, 16, 9, 45), 'Television in the kitchen',
          v3: const ConversationV3Fields(kind: 'media', homeHidden: true, tileState: ConversationTileState.done)),
      _conversation('c-today', DateTime(2026, 11, 16, 9, 0), 'Standup', v3: _done),
      _conversation('c-yesterday', DateTime(2026, 11, 15, 15, 0), 'Design review', v3: _done),
      _conversation('c-yesterday-2', DateTime(2026, 11, 15, 11, 10), 'Lunch with Sam',
          v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.done)),
      // Its summary failed for good: it belongs to Activity, not Home (X5).
      _conversation('c-failed', DateTime(2026, 11, 15, 9, 30), 'Vendor call',
          v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.failed)),
    ]
    ..groupConversationsByDate();
}

Widget _app(_Home home, {Key? boundary, ThemeData? theme}) {
  return RepaintBoundary(
      key: boundary,
      child: MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(value: home.conversations),
          ChangeNotifierProvider<AppProvider>.value(value: AppProvider()),
          ChangeNotifierProvider<CaptureProvider>.value(value: home.capture),
          ChangeNotifierProvider<ConversationsV3Provider>.value(value: home.conversationsV3),
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
            create: (_) => ConversationDetailProvider(fetchConversationResult: home.detailResult),
            update: (_, app, conversations, previous) =>
                (previous?..setProviders(app, conversations)) ??
                ConversationDetailProvider(fetchConversationResult: home.detailResult),
          ),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: theme,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body: ConversationsPage(
              requestInitialLoad: false,
              loadRecaps: () async => (items: <DailySummary>[], ok: true),
              openDaySummary: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
              pendingWork: PendingWorkStore(
                loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
                loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
              ),
            ),
          ),
        ),
      ));
}

Future<_Home> _pumpHome(WidgetTester tester,
    {required bool v3, bool remembered = true, Key? boundary, ThemeData? theme, Size? size}) async {
  tester.view.physicalSize = size ?? const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final home = _Home(v3: v3, remembered: remembered);
  await tester.pumpWidget(_app(home, boundary: boundary, theme: theme));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pump(const Duration(milliseconds: 300));
  return home;
}

Future<void> _dispose(WidgetTester tester, _Home home) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(const Duration(seconds: 1));
  home.capture.dispose();
  home.conversations.dispose();
  home.episodes.dispose();
  home.conversationsV3.dispose();
  home.sync.dispose();
}

class _Conversations extends ConversationProvider {
  _Conversations() : super(isSignedIn: () => false);

  int listReads = 0;
  int forcedReads = 0;
  ApiViewState<List<ServerConversation>>? listStatus;

  @override
  ApiViewState<List<ServerConversation>> get apiViewState => listStatus ?? super.apiViewState;

  @override
  Future<void> forceRefreshConversations({bool reconcileHeldRecordings = false}) async {
    forcedReads++;
    listStatus = null;
    notifyListeners();
  }

  /// Where the last recent-rows re-read started; null until one runs.
  DateTime? recentSince;

  @override
  Future<bool> fetchConversations({bool restoreMergeWatches = true}) async {
    listReads++;
    return true;
  }

  // v3 Home's periodic and capture-event re-reads ask only for recent rows.
  @override
  Future<void> refreshRecentConversations(DateTime since) async {
    listReads++;
    recentSince = since;
  }
}

List<String> _rowIds(WidgetTester tester) =>
    tester.widgetList<ConversationListItem>(find.byType(ConversationListItem)).map((r) => r.conversation.id).toList();

Future<void> settleDetailTab(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pump();
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    SharedPreferences.setMockInitialValues({'uid': 'owner-1'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    AnalyticsManager.configure(_RecordingAdapter());
    await AnalyticsManager.init();
  });
  tearDown(() {
    Env.clearApiBaseUrlOverrideForTesting();
    AnalyticsManager.resetForTesting();
    VisibilityDetectorController.instance.updateInterval = const Duration(milliseconds: 500);
  });

  testWidgets('v3: one flat list, the conversation in progress on top, tiles show the pipeline', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      expect(home.conversationsV3.v3, isTrue);
      expect(home.liveReads, greaterThanOrEqualTo(1));

      expect(_rowIds(tester),
          ['live-1', 'c-call', 'c-transcribing', 'c-writing', 'c-today', 'c-yesterday', 'c-yesterday-2'],
          reason: 'the live conversation leads Today; the hidden and failed ones are off Home (X5)');
      expect(find.byType(LiveEpisodeRow), findsNothing);
      expect(find.byKey(const Key('conversation_tile_live')), findsOneWidget);
      expect(find.byKey(const Key('conversation_tile_writing')), findsOneWidget);
      expect(find.byKey(const Key('conversation_tile_transcribing')), findsOneWidget);
      expect(find.byType(ConversationWritingPen), findsOneWidget);
      expect(find.text('Television in the kitchen'), findsNothing);

      // Yesterday opens its summary; Today has no link.
      expect(find.byType(DaySummaryHeader), findsOneWidget);
      expect(find.byKey(const ValueKey('day_summary_header_2026-11-15')), findsOneWidget);
      expect(find.byKey(const ValueKey('day_summary_header_2026-11-16')), findsNothing);

      expect(home.episodeCalls, 0, reason: 'a v3 account makes no episode calls');

      // The live tile shows the speech so far (11m), the length its detail shows, not start to now (20m).
      final length = tester.widget<Text>(find.byKey(const Key('conversation_row_live_length')));
      expect(length.data, contains('11'));
      expect(length.data, isNot(contains('20')));
      await tester.pump(const Duration(minutes: 3));
      expect(tester.widget<Text>(find.byKey(const Key('conversation_row_live_length'))).data, length.data,
          reason: 'silence after the last words does not grow it');

      // Home stays uncluttered: End lives on the live conversation's detail page, not on its row.
      expect(find.byKey(const Key('live_conversation_end')), findsNothing);
      expect(find.byType(V3LivePlaceholderRow), findsNothing);
      await _dispose(tester, home);
    });
  });

  testWidgets('v3: with nothing listed, the streaming placeholder still opens Today', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.conversations
        ..conversations = []
        ..groupConversationsByDate();
      home.liveOpen = false;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      expect(find.byType(V3LivePlaceholderRow), findsOneWidget);
      final headers = tester.widgetList<DateListItem>(find.byType(DateListItem)).toList();
      expect(headers.map((h) => h.date), [DateTime(_now.year, _now.month, _now.day)], reason: 'one header: Today');
      final today = tester.getRect(find.byType(DateListItem));
      expect(tester.getRect(find.byType(V3LivePlaceholderRow)).top, greaterThanOrEqualTo(today.bottom));
      expect(find.byType(NoConversationsHero), findsNothing, reason: 'something is being captured: not a new account');
      expect(find.byType(EmptyConversationsWidget), findsNothing);
      await _dispose(tester, home);
    });
  });

  testWidgets('v3: a failed live window falls back to one Listening row while streaming', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      final serverRow = find.byKey(const ValueKey('live-1'));
      final placeholder = find.byType(V3LivePlaceholderRow);
      expect(serverRow, findsOneWidget);
      expect(placeholder, findsNothing);
      final top = tester.getTopLeft(serverRow).dy;

      home.conversations
        ..conversations.add(_conversation(
          'live-1',
          home.liveStart,
          'Launch checklist',
          v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.failed),
        ))
        ..groupConversationsByDate();
      home.liveFailed = true;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      expect(serverRow, findsNothing);
      expect(placeholder, findsOneWidget);
      expect(tester.getTopLeft(placeholder).dy, top);

      await _dispose(tester, home);
    });
  });

  testWidgets('v3: a live window Home hides is stood in for by the placeholder; a deleted one is not', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.liveHidden = true;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const ValueKey('live-1')), findsNothing);
      expect(find.byType(V3LivePlaceholderRow), findsOneWidget, reason: 'a hidden live window still reads as live');

      home.liveHidden = false;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      home.conversations.memoriesToDelete['live-1'] = home.conversationsV3.live!;
      home.conversations.notifyListeners();
      await tester.pump();
      expect(find.byKey(const ValueKey('live-1')), findsNothing);
      expect(find.byType(V3LivePlaceholderRow), findsNothing, reason: 'the owner deleted it: nothing stands in');

      // Deleted and hidden at once: still nothing.
      home.liveHidden = true;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      expect(find.byType(V3LivePlaceholderRow), findsNothing, reason: 'a deleted window stays gone when hidden');
      await _dispose(tester, home);
    });
  });

  testWidgets('v3: a live window that started before midnight still leads Today', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.liveStart = DateTime(_now.year, _now.month, _now.day).subtract(const Duration(minutes: 20));
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      expect(_rowIds(tester).first, 'live-1');
      final today =
          tester.getRect(find.byKey(ValueKey('date_${DateTime(_now.year, _now.month, _now.day).toIso8601String()}')));
      final live = tester.getRect(find.byKey(const ValueKey('live-1')));
      expect(live.top, greaterThanOrEqualTo(today.bottom));
      expect(live.top, lessThan(tester.getRect(find.byKey(const ValueKey('c-call'))).top));
      await _dispose(tester, home);
    });
  });

  testWidgets('v3: the open live title is not overwritten while the owner edits it', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.liveTitle = '';
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('live-1')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      final field = find.byType(ConversationTitleField);
      await tester.tap(field);
      await tester.pump();
      home.liveTitle = 'Launch checklist';
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      await tester.pump();
      expect(tester.widget<ConversationTitleField>(field).controller!.text, '',
          reason: 'focused: the server title waits until the owner stops editing');
      await _dispose(tester, home);
    });
  });

  testWidgets('v3: the list is re-read when the conversation in progress closes', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      expect(_rowIds(tester).first, 'live-1');
      final before = home.conversations.listReads;

      home.liveOpen = false;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();

      expect(home.conversationsV3.live, isNull);
      expect(home.conversations.listReads, before + 1,
          reason: 'the closed conversation comes back as an ordinary row from the list read');
      expect(home.conversations.recentSince!.isAfter(home.liveStart), isFalse,
          reason: 'the bounded re-read reaches back to when the closed conversation opened');

      // The pendant is still streaming with no window open: the live row's placeholder stands in, and
      // the pendant capture card does not come back between windows.
      expect(find.byType(V3LivePlaceholderRow), findsOneWidget);
      expect(find.descendant(of: find.byType(ConversationCaptureWidget), matching: find.byType(GestureDetector)),
          findsNothing);
      // It sits under Today, first in the day, never above the day list (David, 2026-11-21).
      final today =
          tester.getRect(find.byKey(ValueKey('date_${DateTime(_now.year, _now.month, _now.day).toIso8601String()}')));
      final placeholder = tester.getRect(find.byType(V3LivePlaceholderRow));
      expect(placeholder.top, greaterThanOrEqualTo(today.bottom), reason: 'the placeholder is inside Today');
      expect(placeholder.top, lessThan(tester.getRect(find.byKey(const ValueKey('c-call'))).top),
          reason: 'and leads it');

      // The next window opens: its row replaces the placeholder in the same slot, so nothing jumps.
      home.liveOpen = true;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      expect(find.byType(V3LivePlaceholderRow), findsNothing);
      expect(_rowIds(tester).first, 'live-1');
      expect(tester.getRect(find.byKey(const ValueKey('live-1'))).top, placeholder.top,
          reason: 'the live row takes the placeholder\'s slot');
      await _dispose(tester, home);
    });
  });

  testWidgets('first launch: a v3 account makes no episode call before the switch answers', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true, remembered: false);
      expect(home.conversationsV3.v3, isTrue);
      expect(_rowIds(tester).first, 'live-1');
      expect(home.episodeCalls, 0);
      await _dispose(tester, home);
    });
  });

  testWidgets('first launch, not v3: episodes start once the switch says so', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: false, remembered: false);
      expect(home.conversationsV3.resolved, isTrue);
      expect(home.episodeCalls, greaterThan(0));
      expect(find.byType(DaySummaryHeader), findsNothing);
      await _dispose(tester, home);
    });
  });

  testWidgets('v3 off: Home is unchanged, with the live episode and plain day labels', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: false);
      expect(home.conversationsV3.v3, isFalse);
      expect(find.byType(DaySummaryHeader), findsNothing);
      expect(find.byType(LiveEpisodeRow), findsOneWidget, reason: "today's live episode row");
      expect(find.byType(ConversationWritingPen), findsNothing);
      expect(_rowIds(tester), isNot(contains('live-1')));
      expect(home.episodeCalls, greaterThan(0));
      await _dispose(tester, home);
    });
  });

  final endButton = find.byKey(const Key('live_conversation_end'));
  final finishButton = find.byKey(const Key('process_now_button'));
  final visibleHomeFinish = find.text('Finish').hitTestable();

  testWidgets('v3: Home live rows open their pages without showing a Finish pill', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      final row = find.byKey(const ValueKey('live-1'));
      expect(row, findsOneWidget);
      expect(visibleHomeFinish, findsNothing);
      expect(endButton, findsNothing);

      home.liveOpen = false;
      await home.conversationsV3.refresh();
      await tester.pump();
      expect(find.byType(V3LivePlaceholderRow), findsOneWidget);
      expect(visibleHomeFinish, findsNothing);
      expect(endButton, findsNothing);
      await _dispose(tester, home);
    });
  });

  testWidgets('Home updates the live row when only its recording IDs change', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      final row = find.byKey(const ValueKey('live-1'));
      List<String> recordingIds() => tester.widget<ConversationListItem>(row).conversation.v3!.recordingIds;
      expect(recordingIds(), ['rec-1']);

      home.liveRecordingIds = ['rec-2'];
      await home.conversationsV3.refresh();
      await tester.pump();
      expect(recordingIds(), ['rec-2']);

      await _dispose(tester, home);
    });
  });

  testWidgets('a failed End releases suppression even when ownership changes during the drain', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.capture.verifiedLiveServerRecordingId = 'rec-1';
      home.publishManualEnds();
      final drain = home.capture.drain = Completer<void>();
      final conversation = home.conversationsV3.live!;
      final suppression = <bool>[];
      final navigator = Navigator.of(tester.element(find.byType(ConversationsPage)));
      unawaited(navigator.push(omiPageRoute(
        builder: (_) => Scaffold(
          body: Center(
            child: LiveConversationEndButton(conversation: conversation, onEndSuppressionChanged: suppression.add),
          ),
        ),
      )));
      await settleDetailTab(tester);

      await tester.tap(endButton);
      await tester.pump();
      expect(suppression, [true]);
      home.capture
        ..verifiedLiveServerRecordingId = 'rec-2'
        ..ping();
      await tester.pump();
      expect(endButton, findsNothing);
      drain.completeError(StateError('WAL drain failed'));
      await settleDetailTab(tester);
      expect(suppression, [true, false]);

      home.capture
        ..verifiedLiveServerRecordingId = 'rec-1'
        ..ping();
      await tester.pump();
      expect(endButton.hitTestable(), findsOneWidget);
      await _dispose(tester, home);
    });
  });

  testWidgets('v3: the placeholder opens Finish for a verified capture with no transcript', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.liveOpen = false;
      home.capture
        ..segments = []
        ..verifiedLiveServerRecordingId = 'rec-1';
      home.publishManualEnds();
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.tap(find.byType(V3LivePlaceholderRow));
      await settleDetailTab(tester);
      expect(find.byType(LiveEpisodePage), findsOneWidget);
      expect(finishButton.hitTestable(), findsOneWidget);

      await tester.tap(finishButton);
      await settleDetailTab(tester);
      await tester.pump(const Duration(milliseconds: 500));
      expect(home.capture.finishCalls, 1);
      expect(home.capture.finishedLiveId, isNull);
      expect(find.byType(LiveEpisodePage), findsNothing);
      expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
      await _dispose(tester, home);
    });
  });

  testWidgets("End is hidden on a live window that is not this phone's capture", (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      // The account-wide read can load another device's window and transcript on this phone.
      home.capture
        ..segmentsFromSocket = false
        ..topConversationId = 'rec-1'
        ..verifiedLiveServerRecordingId = 'other-recording'
        ..applyInProgressConversation(home.conversationsV3.live!);
      expect(home.capture.segments, isNotEmpty);
      await tester.tap(find.text('Launch checklist'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byKey(const ValueKey('detail_ask_omi')), findsOneWidget);
      expect(find.byKey(const Key('live_conversation_end')), findsNothing,
          reason: "End would finalize this phone's capture, not the conversation on screen");
      expect(home.capture.endCalls, 0);
      await _dispose(tester, home);
    });
  });

  for (final overlapping in [false, true]) {
    testWidgets(
        'End is hidden on the earlier window after the server rotates its recording'
        '${overlapping ? ' even with overlapping local segments' : ''}', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        final home = await _pumpHome(tester, v3: true);
        if (!overlapping) {
          home.detailSegments = [];
          home.capture.segments = [];
        }
        // The earlier window still lists the client capture ID; the verified server ID has moved on.
        home.liveRecordingIds = [home.capture.activeRecordingId!];
        await home.conversationsV3.refresh();
        home.capture.verifiedLiveServerRecordingId = 'rec-next';
        await tester.tap(find.text('Launch checklist'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byKey(const ValueKey('detail_ask_omi')), findsOneWidget);
        expect(find.byKey(const Key('live_conversation_end')), findsNothing);
        expect(home.capture.endCalls, 0);
        await _dispose(tester, home);
      });
    });
  }

  for (final verified in [false, true]) {
    testWidgets('End uses the ${verified ? 'verified server' : 'active capture'} ID with no local transcript',
        (tester) async {
      await withClock(Clock.fixed(_now), () async {
        final home = await _pumpHome(tester, v3: true);
        home.detailSegments = [];
        home.capture.segments = [];
        if (verified) {
          home.capture.verifiedLiveServerRecordingId = 'rec-1';
        } else {
          home.liveRecordingIds = [home.capture.activeRecordingId!];
          await home.conversationsV3.refresh();
          expect(home.conversationsV3.live!.v3!.recordingIds, home.liveRecordingIds);
        }
        home.publishManualEnds();
        Future<bool> openRoute(String route, {bool Function()? canOpen}) async => false;
        HomeNavigation.register(openRoute);
        addTearDown(() => HomeNavigation.unregister(openRoute));
        await tester.tap(find.text('Launch checklist'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.pump(const Duration(milliseconds: 500));
        expect(endButton.hitTestable(), findsOneWidget);
        expect(home.capture.segments, isEmpty);
        if (!verified) {
          final activeId = home.capture.activeRecordingId;
          // Remove the ownership evidence without notifying so the previous frame still has End.
          home.capture.activeRecordingId = 'replacement-capture';
          await tester.tap(endButton);
          expect(home.capture.endCalls, 0);
          home.capture.activeRecordingId = activeId;
        }
        await tester.tap(endButton);
        expect(home.capture.endCalls, 1);
        expect(home.capture.endedLiveId, 'live-1');
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(ConversationDetailPage), findsNothing);
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        await _dispose(tester, home);
      });
    });
  }

  final recapSpeech = [
    TranscriptSegment(
      id: 'eligible',
      text: List.filled(300, 'speech').join(' '),
      speaker: 'SPEAKER_00',
      personId: null,
      isUser: true,
      start: 0,
      end: 60,
      translations: [],
    ),
  ];

  testWidgets('a denied live detail refresh removes a visible recap', (tester) async {
    final home = await _pumpHome(tester, v3: true);
    home.detailSegments = recapSpeech;
    LiveSummarySection.debugStream =
        (_) => Stream.value(SummaryDone(Structured('Recap', 'Visible before denial.'), _now));
    addTearDown(() => LiveSummarySection.debugStream = null);
    await tester.tap(find.text('Launch checklist'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(find.textContaining('Visible before denial.'), findsOneWidget);
    home.detailDenied = true;
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    expect(find.textContaining('Visible before denial.'), findsNothing);
    expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
    await _dispose(tester, home);
  });

  testWidgets('the first settled Summary tap can use its pending initial hydration once', (tester) async {
    final home = await _pumpHome(tester, v3: true);
    final hydrate = Completer<void>();
    home.detailBarrier = hydrate;
    home.detailSegments = recapSpeech;
    final requests = <LiveRecapRequest>[];
    int opens() => requests.length;
    LiveSummarySection.debugLiveStream = (_, recap) {
      requests.add(recap);
      return Stream.value(const SummaryFailed('synthetic'));
    };
    addTearDown(() => LiveSummarySection.debugLiveStream = null);

    await tester.tap(find.text('Launch checklist'));
    await settleDetailTab(tester);
    expect(opens(), 0);
    await tester.tap(find.text('Summary'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(opens(), 0, reason: 'the tab has not settled');
    await settleDetailTab(tester);
    expect(opens(), 0, reason: 'initial authoritative data has not arrived');
    hydrate.complete();
    await settleDetailTab(tester);
    expect(opens(), 1);
    await tester.tap(find.byKey(const Key('live_summary_catch_up')));
    await settleDetailTab(tester);
    expect(opens(), 2, reason: 'a retry in the same continuous visit is a new request');
    expect(requests.first.intervalId, requests[1].intervalId);
    expect(requests.first.requestId, isNot(requests[1].requestId));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    expect(opens(), 2, reason: 'resume and periodic refresh cannot spend');
    await tester.tap(find.text('Transcript'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(opens(), 2, reason: 'an attempted recap does not auto-retry');
    await tester.tap(find.byKey(const Key('live_summary_catch_up')));
    await settleDetailTab(tester);
    expect(opens(), 3, reason: 'explicit retry is allowed');
    expect(
        requests.map((r) => r.trigger), [LiveRecapTrigger.firstOpen, LiveRecapTrigger.retry, LiveRecapTrigger.retry]);
    expect(requests[1].intervalId, isNot(requests.last.intervalId));
    expect(requests.map((r) => r.requestId).toSet(), hasLength(3));
    await _dispose(tester, home);
  });

  testWidgets('live recap refresh requires uninterrupted foreground Summary viewing and new speech', (tester) async {
    final home = await _pumpHome(tester, v3: true);
    home.detailSegments = recapSpeech;
    final requests = <LiveRecapRequest>[];
    int opens() => requests.length;
    LiveSummarySection.debugLiveStream = (_, recap) {
      requests.add(recap);
      return Stream.value(
          SummaryDone(Structured('Recap', 'Recap ${opens()}'), _now.subtract(const Duration(minutes: 19))));
    };
    addTearDown(() => LiveSummarySection.debugLiveStream = null);
    await tester.tap(find.text('Launch checklist'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(opens(), 1);
    await tester.pump(const Duration(minutes: 5));
    await settleDetailTab(tester);
    expect(opens(), 1, reason: 'unchanged transcript');
    home.detailSegments = [
      ...recapSpeech,
      TranscriptSegment(
          id: 'new',
          text: 'New speech.',
          start: 661,
          end: 664,
          speaker: 'SPEAKER_00',
          isUser: true,
          personId: null,
          translations: [])
    ];
    await tester.pump(const Duration(minutes: 4));
    await settleDetailTab(tester);
    await tester.tap(find.text('Transcript'));
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 6));
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 4));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump(const Duration(minutes: 6));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await settleDetailTab(tester);
    final navigator = tester.state<NavigatorState>(find.byType(Navigator).first);
    await tester.pump(const Duration(minutes: 4));
    unawaited(navigator.push(MaterialPageRoute<void>(builder: (_) => const SizedBox())));
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 6));
    navigator.pop();
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 4, seconds: 58));
    await settleDetailTab(tester);
    expect(opens(), 1, reason: 'each interruption resets the five-minute interval');
    await tester.pump(const Duration(seconds: 3));
    await settleDetailTab(tester);
    expect(opens(), 2);
    await tester.pump(const Duration(minutes: 5));
    await settleDetailTab(tester);
    expect(opens(), 2, reason: 'no duplicate generation');
    expect(requests.map((r) => r.trigger), [LiveRecapTrigger.firstOpen, LiveRecapTrigger.timedRefresh]);
    expect(requests.first.intervalId, isNot(requests.last.intervalId));
    expect(requests.first.requestId, isNot(requests.last.requestId));
    final uuidV4 = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$');
    for (final request in requests) {
      expect(request.requestId, matches(uuidV4));
      expect(request.intervalId, matches(uuidV4));
    }
    await _dispose(tester, home);
  });

  testWidgets('hidden or ineligible live detail cancels the interval before any timed request', (tester) async {
    final home = await _pumpHome(tester, v3: true);
    home.detailSegments = recapSpeech;
    final requests = <LiveRecapRequest>[];
    LiveSummarySection.debugLiveStream = (_, recap) {
      requests.add(recap);
      return Stream.value(
          SummaryDone(Structured('Recap', 'Visible recap.'), _now.subtract(const Duration(minutes: 19))));
    };
    addTearDown(() => LiveSummarySection.debugLiveStream = null);
    await tester.tap(find.text('Launch checklist'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(requests, hasLength(1));

    await tester.pump(const Duration(minutes: 4));
    home.detailHidden = true;
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 6));
    await settleDetailTab(tester);
    expect(requests, hasLength(1));

    home.detailHidden = false;
    home.detailSegments = _liveSoFar;
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 6));
    await settleDetailTab(tester);
    expect(requests, hasLength(1), reason: 'short speech never starts an interval');
    home.detailSegments = [
      ...recapSpeech,
      TranscriptSegment(
          id: 'new',
          text: 'New eligible speech.',
          start: 661,
          end: 664,
          speaker: 'SPEAKER_00',
          isUser: true,
          personId: null,
          translations: []),
    ];
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    await tester.pump(const Duration(minutes: 4, seconds: 58));
    await settleDetailTab(tester);
    expect(requests, hasLength(1));
    await tester.pump(const Duration(seconds: 3));
    await settleDetailTab(tester);
    expect(requests, hasLength(2));
    expect(requests.last.trigger, LiveRecapTrigger.timedRefresh);
    expect(requests.last.intervalId, isNot(requests.first.intervalId));
    await _dispose(tester, home);
  });

  testWidgets('restoring directly to Summary does not generate a live recap', (tester) async {
    final home = await _pumpHome(tester, v3: true);
    home.detailSegments = recapSpeech;
    final restored = (await home.detailRead('live-1'))!;
    var opens = 0;
    LiveSummarySection.debugStream = (_) {
      opens++;
      return Stream.value(const SummaryFailed('synthetic'));
    };
    addTearDown(() => LiveSummarySection.debugStream = null);

    final navigator = tester.state<NavigatorState>(find.byType(Navigator).first);
    unawaited(navigator.push(MaterialPageRoute<void>(
      builder: (_) => ConversationDetailPage(conversation: restored, initialTab: ConversationTab.summary),
    )));
    await settleDetailTab(tester);
    expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
    expect(opens, 0);
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    expect(opens, 0, reason: 'the restored tab and its passive refresh are not deliberate selection');
    await _dispose(tester, home);
  });

  for (final retained in [false, true]) {
    testWidgets('End during hydration cancels intent and restores recap only for a retained capture: $retained',
        (tester) async {
      final home = await _pumpHome(tester, v3: true);
      home.publishManualEnds();
      final hydrate = Completer<void>();
      final drain = retained ? (home.capture.drain = Completer<void>()) : null;
      home.detailBarrier = hydrate;
      home.detailSegments = recapSpeech;
      var opens = 0;
      LiveSummarySection.debugStream = (_) {
        opens++;
        return Stream.value(const SummaryFailed('synthetic'));
      };
      addTearDown(() => LiveSummarySection.debugStream = null);

      await tester.tap(find.text('Launch checklist'));
      await settleDetailTab(tester);
      // Filtered Home cannot show Processing, so a successful End stays on detail.
      home.conversations.showStarredOnly = true;
      await tester.tap(find.text('Summary'));
      await settleDetailTab(tester);
      expect(opens, 0);
      await tester.tap(find.byKey(const Key('live_conversation_end')));
      expect(home.capture.endCalls, 1);
      hydrate.complete();
      await settleDetailTab(tester);
      expect(opens, 0);
      drain?.completeError(StateError('WAL drain failed'));
      await settleDetailTab(tester);
      expect(opens, 0, reason: 'settling End must never spend');
      await tester.tap(find.text('Transcript'));
      await settleDetailTab(tester);
      await tester.tap(find.text('Summary'));
      await settleDetailTab(tester);
      expect(opens, retained ? 1 : 0);
      await _dispose(tester, home);
    });
  }

  testWidgets('passive growth cannot upgrade a short Summary selection to a recap', (tester) async {
    final home = await _pumpHome(tester, v3: true, size: const Size(393, 852));
    var opens = 0;
    LiveSummarySection.debugStream = (_) {
      opens++;
      return Stream.value(const SummaryFailed('synthetic'));
    };
    addTearDown(() => LiveSummarySection.debugStream = null);
    await tester.tap(find.text('Launch checklist'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(opens, 0);
    expect(find.byKey(const Key('live_summary_recent_transcript')), findsOneWidget);
    home.detailSegments = recapSpeech;
    await tester.pump(const Duration(seconds: 15));
    await settleDetailTab(tester);
    expect(opens, 0, reason: 'passive refresh is never intent');

    await tester.tap(find.text('Transcript'));
    await settleDetailTab(tester);
    final tabs = find.byType(TabBarView);
    final pageScrollable = find.descendant(of: tabs, matching: find.byType(Scrollable)).first;
    final position = tester.state<ScrollableState>(pageScrollable).position;
    final before = position.pixels;
    final box = tester.getRect(tabs);
    final gesture = await tester.startGesture(Offset(box.left + 72, box.top + 24));
    await gesture.moveBy(const Offset(30, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(100, 0));
    await tester.pump(const Duration(milliseconds: 100));
    expect(position.pixels, lessThan(before), reason: 'the actual PageView is partway into a swipe');
    expect(position.pixels, greaterThan(0));
    expect(opens, 0, reason: 'a swipe in progress may prebuild Summary without permission');
    await gesture.cancel();
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await settleDetailTab(tester);
    expect(position.pixels, closeTo(before, 1));
    expect(opens, 0);

    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(opens, 1, reason: 'a later deliberate settled selection is eligible');
    await _dispose(tester, home);
  });

  testWidgets('a failed initial detail read can recover without spending on hydration alone', (tester) async {
    final home = await _pumpHome(tester, v3: true);
    home.detailFails = true;
    var opens = 0;
    LiveSummarySection.debugStream = (_) {
      opens++;
      return Stream.value(const SummaryFailed('synthetic'));
    };
    addTearDown(() => LiveSummarySection.debugStream = null);
    await tester.tap(find.text('Launch checklist'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(opens, 0);
    expect(find.byKey(const Key('live_summary_detail_retry')), findsOneWidget);
    home.detailFails = false;
    home.detailSegments = recapSpeech;
    await tester.tap(find.byKey(const Key('live_summary_detail_retry')));
    await settleDetailTab(tester);
    expect(opens, 0);
    await tester.tap(find.text('Transcript'));
    await settleDetailTab(tester);
    await tester.tap(find.text('Summary'));
    await settleDetailTab(tester);
    expect(opens, 1);
    await _dispose(tester, home);
  });

  testWidgets('the live page opened on Transcript keeps re-reading until the summary is being written', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      await tester.tap(find.text('Launch checklist'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(SummaryTab), findsNothing, reason: 'it opens on Transcript; Summary is not built');
      final atOpen = home.detailReads;
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      expect(home.detailReads, atOpen + 1, reason: 'the page, not the Summary tab, keeps a live window current');

      // It ended; its transcript is still arriving. The page keeps reading.
      home.detailState = ConversationTileState.transcribing;
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      expect(home.detailReads, atOpen + 3);

      // Its summary is being written: the page has seen it move on and stops re-reading.
      home.detailState = ConversationTileState.writing;
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      expect(home.detailReads, atOpen + 4);
      await _dispose(tester, home);
    });
  });

  testWidgets('an untitled live conversation reads Listening, and its open page takes the title when it lands',
      (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.liveTitle = '';
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();

      // The row reads like the placeholder: "Listening" over "Live · 11m", never a date or a snippet.
      final live = find.byKey(const ValueKey('live-1'));
      expect(find.descendant(of: live, matching: find.text('Listening')), findsOneWidget);
      expect(tester.widget<Text>(find.byKey(const Key('conversation_row_live_length'))).data, 'Live · 11m');
      expect(find.descendant(of: live, matching: find.textContaining('2026')), findsNothing);
      expect(find.descendant(of: live, matching: find.textContaining('Doors')), findsNothing);

      await tester.tap(live);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      final field = find.byType(ConversationTitleField);
      expect(tester.widget<ConversationTitleField>(field).hintText, 'Listening');

      // The server names it; the page's 15 s re-read brings the title into the open page.
      home.liveTitle = 'Launch checklist';
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      await tester.pump();
      expect(tester.widget<ConversationTitleField>(field).controller!.text, 'Launch checklist');
      await _dispose(tester, home);
    });
  });

  testWidgets('the live page opened from the placeholder reads Listening, then the server title', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true);
      home.liveOpen = false;
      await home.conversationsV3.refresh();
      await tester.pump();
      await tester.pump();
      await tester.tap(find.byType(V3LivePlaceholderRow));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      final title = find.byKey(const Key('live_page_v3_title'));
      expect(find.descendant(of: title, matching: find.text('Listening')), findsOneWidget);

      // Home stops re-reading while the page covers it; the page re-reads and takes the title.
      home.liveOpen = true;
      await tester.pump(const Duration(seconds: 15));
      await tester.pump();
      await tester.pump();
      expect(find.descendant(of: title, matching: find.text('Launch checklist')), findsOneWidget);
      await _dispose(tester, home);
    });
  });

  testWidgets('a 320pt phone: the live detail bar fits Ask Omi and End', (tester) async {
    await withClock(Clock.fixed(_now), () async {
      final home = await _pumpHome(tester, v3: true, size: const Size(320, 640));
      await tester.tap(find.text('Launch checklist'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.takeException(), isNull, reason: 'no overflow in the bar');
      expect(find.byKey(const Key('live_conversation_end')), findsOneWidget);
      expect(tester.getSize(find.byKey(const Key('live_conversation_end'))).width, lessThanOrEqualTo(320 * 0.45 + 2),
          reason: 'at most about half the bar, border included');
      await _dispose(tester, home);
    });
  });

  group('render evidence (written when V3_HOME_RENDER_OUTPUT is set; a layout check otherwise)', () {
    const output = String.fromEnvironment('V3_HOME_RENDER_OUTPUT');
    final boundary = GlobalKey();

    setUpAll(_loadFonts);

    Future<void> shoot(WidgetTester tester, String name) async {
      expect(tester.takeException(), isNull, reason: '$name rendered with an exception');
      if (output.isEmpty) return;
      await tester.runAsync(() async {
        final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
      });
    }

    ThemeData theme([Brightness brightness = Brightness.dark]) {
      final base = buildOmiTheme(brightness: brightness);
      return base.copyWith(
        appBarTheme: base.appBarTheme.copyWith(
          titleTextStyle: base.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
        ),
      );
    }

    testWidgets('Home explains that conversations require a recording device', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.capture.streaming = false;
        home.capture.notifyListeners();
        home.liveOpen = false;
        await home.conversationsV3.refresh();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        expect(find.text('Pair your Omi and it captures your conversations hands-free, all day.'), findsOneWidget);
        expect(find.text('Connect Device'), findsOneWidget);
        expect(find.bySemanticsLabel('Start Recording'), findsNothing);
        await shoot(tester, '001-mobile-ios-connect-recording-device');
        await _dispose(tester, home);
      });
    });

    testWidgets('a list read failure keeps Try Again beside a manual finish', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.conversations.conversations.clear();
        home.conversations.listStatus = const ApiViewState(
          phase: ApiViewPhase.error,
          problem: ApiProblem(ApiProblemKind.server, statusCode: 503),
        );
        home.conversations.groupConversationsByDate();
        home.publishManualEnds();
        home.capture.onManualEnd!('live-1');
        await tester.pump();

        expect(find.byKey(const ValueKey('omi.conversations.error')), findsOneWidget);
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        await shoot(tester, '003-mobile-ios-finish-list-retry');
        await tester.tap(find.text('Try Again'));
        await tester.pump();
        expect(home.conversations.forcedReads, 1);
        expect(find.byKey(const ValueKey('omi.conversations.error')), findsNothing);
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        await _dispose(tester, home);
        debugDefaultTargetPlatformOverride = null;
      });
    });

    testWidgets('End from a deep link stays on detail when a Home filter would hide Processing', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.publishManualEnds();
        final drain = home.capture.drain = Completer<void>();
        final context = tester.element(find.byType(ConversationsPage));
        final tabs = context.read<HomeProvider>()..setIndex(HomeProvider.tasksTab);
        home.conversations.showStarredOnly = true;
        home.capture
          ..verifiedLiveServerRecordingId = 'rec-1'
          ..keepVerifiedAfterClose = true;
        final navigator = Navigator.of(context);
        Future<bool> openRoute(String route, {bool Function()? canOpen}) async {
          unawaited(navigator.push(omiPageRoute(
            builder: (_) => ConversationDetailPage(conversation: home.conversationsV3.live!),
          )));
          return true;
        }

        HomeNavigation.register(openRoute);
        addTearDown(() => HomeNavigation.unregister(openRoute));
        expect(await HomeNavigation.openRoute('/conversation/live-1', navigator: navigator), isTrue);
        await settleDetailTab(tester);
        await tester.tap(find.byKey(const Key('live_conversation_end')));
        await settleDetailTab(tester);
        drain.complete();
        await settleDetailTab(tester);
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(ConversationDetailPage), findsOneWidget, reason: 'starred Home cannot show Processing');
        expect(tabs.selectedIndex, HomeProvider.tasksTab);
        final calls = home.capture.endCalls;
        final end = find.byKey(const Key('live_conversation_end'));
        expect(end, findsOneWidget, reason: 'the verified recording still owns this detail');
        await tester.tap(end, warnIfMissed: false);
        await tester.pump();
        expect(home.capture.endCalls, calls, reason: 'a closed window keeps End latched');

        // The detached server finalize fails: End is released for a retry.
        expect(home.conversationsV3.settleManualFinish(home.conversationsV3.finishRow!, null), isTrue);
        await tester.pump();
        await tester.pump();
        home.capture.drain = null;
        await tester.tap(end, warnIfMissed: false);
        await tester.pump();
        expect(home.capture.endCalls, calls + 1, reason: 'an unsuccessful settlement releases End');
        home.conversations.showStarredOnly = false;
        await _dispose(tester, home);
      });
    });

    testWidgets('End from a deep link selects Home after the drain', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.publishManualEnds();
        final drain = home.capture.drain = Completer<void>();
        final context = tester.element(find.byType(ConversationsPage));
        final tabs = context.read<HomeProvider>()..setIndex(HomeProvider.tasksTab);
        final navigator = Navigator.of(context);
        Future<bool> openRoute(String route, {bool Function()? canOpen}) async {
          unawaited(navigator.push(omiPageRoute(
            builder: (_) => ConversationDetailPage(conversation: home.conversationsV3.live!),
          )));
          return true;
        }

        HomeNavigation.register(openRoute);
        addTearDown(() => HomeNavigation.unregister(openRoute));
        expect(await HomeNavigation.openRoute('/conversation/live-1', navigator: navigator), isTrue);
        await settleDetailTab(tester);
        final end = find.byKey(const Key('live_conversation_end'));
        await tester.tap(end);
        await settleDetailTab(tester);
        expect(end, findsOneWidget, reason: 'End stays until the close succeeds');
        expect(tabs.selectedIndex, HomeProvider.tasksTab);

        drain.complete();
        await settleDetailTab(tester);
        await tester.pump(const Duration(milliseconds: 500));
        expect(tabs.selectedIndex, HomeProvider.homeTab);
        expect(find.byType(ConversationDetailPage), findsNothing);
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        await shoot(tester, '004-mobile-ios-end-returns-home');
        await _dispose(tester, home);
        debugDefaultTargetPlatformOverride = null;
      });
    });

    testWidgets('a failed drain after publishing Processing leaves End available to retry', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.publishManualEnds();
        final drain = home.capture.drain = Completer<void>();
        await tester.tap(find.text('Launch checklist'));
        await settleDetailTab(tester);
        final end = find.byKey(const Key('live_conversation_end'));
        await tester.tap(end);
        await settleDetailTab(tester);
        expect(home.conversationsV3.finishRow, isNotNull);
        expect(end, findsOneWidget);
        await tester.tap(end);
        expect(home.capture.endCalls, 1, reason: 'only one drain can run at a time');

        drain.completeError(StateError('WAL drain failed'));
        await settleDetailTab(tester);
        expect(home.conversationsV3.finishRow, isNull);
        expect(find.byType(ConversationDetailPage), findsOneWidget);
        expect(end, findsOneWidget);
        expect(find.byType(SnackBar), findsNothing);
        await tester.tap(find.text('Summary'));
        await settleDetailTab(tester);
        expect(find.text('Recent transcript'), findsOneWidget);
        await shoot(tester, '005-mobile-ios-end-retry-after-drain');

        home.capture.drain = Completer<void>();
        await tester.tap(end);
        expect(home.capture.endCalls, 2);
        expect(home.conversationsV3.finishRow, isNotNull);
        home.capture.drain!.completeError(StateError('WAL drain failed again'));
        await settleDetailTab(tester);
        await _dispose(tester, home);
        debugDefaultTargetPlatformOverride = null;
      });
    });

    testWidgets('End on a live detail with no local segments returns to Processing', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        addTearDown(() => debugDefaultTargetPlatformOverride = null);
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.capture.segments = [];
        home.detailSegments = [];
        home.liveRecordingIds = [home.capture.activeRecordingId!];
        home.publishManualEnds();
        // The test harness already supplies Home as its root route.
        Future<bool> openRoute(String route, {bool Function()? canOpen}) async => false;
        HomeNavigation.register(openRoute);
        addTearDown(() => HomeNavigation.unregister(openRoute));
        await home.conversationsV3.refresh();
        await tester.pump();
        expect(visibleHomeFinish, findsNothing);
        await tester.tap(find.text('Launch checklist'));
        await settleDetailTab(tester);
        await tester.pump(const Duration(milliseconds: 500));
        expect(home.capture.segments, isEmpty);
        expect(endButton.hitTestable(), findsOneWidget);
        await shoot(tester, '001-mobile-ios-live-detail-end');

        await tester.tap(endButton);
        await settleDetailTab(tester);
        await tester.pump(const Duration(milliseconds: 500));
        expect(home.capture.endCalls, 1);
        expect(home.capture.endedLiveId, 'live-1');
        expect(find.byType(ConversationDetailPage), findsNothing);
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        expect(find.byType(SnackBar), findsNothing);
        await shoot(tester, '003-mobile-ios-home-processing-after-end');
        await _dispose(tester, home);
        debugDefaultTargetPlatformOverride = null;
      });
    });

    for (final placeholder in [false, true]) {
      testWidgets('the next live ${placeholder ? 'placeholder' : 'server row'} can finish while Home shows Processing',
          (tester) async {
        await withClock(Clock.fixed(_now), () async {
          debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
          addTearDown(() => debugDefaultTargetPlatformOverride = null);
          final palette = OmiColors.active;
          addTearDown(() => OmiColors.active = palette);
          OmiColors.active = OmiColors.forBrightness(Brightness.dark);
          final home =
              await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
          home.capture
            ..verifiedLiveServerRecordingId = 'rec-1'
            ..keepVerifiedAfterClose = true;
          home.publishManualEnds();
          Future<bool> openRoute(String route, {bool Function()? canOpen}) async => false;
          HomeNavigation.register(openRoute);
          addTearDown(() => HomeNavigation.unregister(openRoute));

          await tester.tap(find.byKey(const ValueKey('live-1')));
          await settleDetailTab(tester);
          await tester.tap(endButton);
          await settleDetailTab(tester);
          final firstFinish = home.conversationsV3.finishRow!;
          expect(home.capture.endedLiveId, 'live-1');
          expect(
              home.conversationsV3.settleManualFinish(
                firstFinish,
                _conversation('rec-1', _now, '', v3: const ConversationV3Fields(recording: true)),
              ),
              isTrue);
          home.capture.closedRecordingIds.add('rec-1');
          expect(find.byKey(const Key('home_processing_row')), findsOneWidget);

          // The pendant keeps its client capture ID. Home reads the successor before
          // the socket delivers its new conversation_session event.
          home.liveId = 'live-2';
          home.liveTitle = '';
          home.liveStart = _now.subtract(const Duration(minutes: 10));
          home.liveRecordingIds = ['rec-2'];
          final nextLine = _said('next-line', 'The sound check starts at five.', 0, 2);
          home.detailSegments = [nextLine];
          home.capture
            ..recordingToProcess = 'rec-2'
            ..segments = [nextLine]
            ..segmentsFromSocket = false
            ..ping();
          await home.conversationsV3.refresh();
          await settleDetailTab(tester);

          if (placeholder) {
            // Home hides the window and offers the local capture page. The window
            // still lists the active capture ID, the only available ownership evidence.
            home.liveHidden = true;
            final activeId = home.capture.activeRecordingId!;
            home.liveRecordingIds = [activeId];
            home.capture
              ..recordingToProcess = activeId
              ..segments = []
              ..verifiedLiveServerRecordingId = null
              ..ping();
            await home.conversationsV3.refresh();
            await settleDetailTab(tester);
          }
          final nextRow = placeholder ? find.byType(V3LivePlaceholderRow) : find.byKey(const ValueKey('live-2'));
          expect(nextRow, findsOneWidget);
          expect(find.descendant(of: nextRow, matching: find.text('Listening')), findsOneWidget);
          expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
          if (!placeholder) {
            await tester.drag(nextRow, const Offset(-200, 0));
            await settleDetailTab(tester);
            expect(visibleHomeFinish, findsNothing);
            await shoot(tester, '004-mobile-ios-listening-and-processing');
          }
          await tester.tap(nextRow);
          await settleDetailTab(tester);
          await tester.pump(const Duration(milliseconds: 500));
          expect(placeholder ? find.byType(LiveEpisodePage) : find.byType(ConversationDetailPage), findsOneWidget);
          final action = placeholder ? finishButton : endButton;
          if (!placeholder) {
            expect(action, findsNothing, reason: 'the account-wide transcript alone cannot prove ownership');
            home.capture
              ..segmentsFromSocket = true
              ..ping();
            await settleDetailTab(tester);
          }
          expect(action.hitTestable(), findsOneWidget);
          await shoot(
              tester, placeholder ? '006-mobile-ios-next-placeholder-finish' : '005-mobile-ios-next-detail-end');
          await tester.tap(action);
          await settleDetailTab(tester);
          if (placeholder) {
            expect(home.capture.finishCalls, 1);
            expect(home.capture.finishedRecordingId, home.capture.activeRecordingId);
            expect(home.capture.finishedLiveId, 'live-2');
            expect(home.capture.endCalls, 1);
          } else {
            expect(home.capture.endCalls, 2);
            expect(home.capture.endedLiveId, 'live-2');
          }
          expect(home.conversationsV3.finishRow, isNotNull);
          expect(home.conversationsV3.finishRow, isNot(same(firstFinish)));
          await _dispose(tester, home);
          debugDefaultTargetPlatformOverride = null;
        });
      });
    }

    testWidgets('a new live row leads Today while the previous window is processing', (tester) async {
      final date = DateTime.now();
      final todayAtNoon = DateTime(date.year, date.month, date.day, 12);
      await withClock(Clock.fixed(todayAtNoon), () async {
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        // The date label uses the device clock, so seed a finished row on its Today.
        home.conversations.conversations = [
          _conversation('today-call', todayAtNoon.subtract(const Duration(minutes: 5)), 'Call from the printer',
              v3: null),
        ];
        home.conversations.groupConversationsByDate();
        final today = find.text('Today');
        final listening = find.text('Listening');
        final processing = find.byKey(const Key('home_processing_row'));
        final call = find.byKey(const ValueKey('today-call'));

        void expectOrder(List<Finder> rows) {
          for (final row in rows) {
            expect(row, findsOneWidget);
          }
          for (var i = 1; i < rows.length; i++) {
            expect(tester.getBottomLeft(rows[i - 1]).dy, lessThanOrEqualTo(tester.getTopLeft(rows[i]).dy));
          }
        }

        home.publishManualEnds();
        final pending = home.capture.onManualEnd!('live-1');
        await tester.pump();
        expect(home.conversationsV3.finishRow, same(pending));
        expect(find.byKey(const ValueKey('live-1')), findsNothing);
        expect(find.byType(V3LivePlaceholderRow), findsNothing);
        expectOrder([today, processing, call]);
        expect(find.descendant(of: processing, matching: find.text('Processing…')), findsOneWidget);

        home.liveOpen = false;
        await home.conversationsV3.refresh();
        home.capture.activeRecordingId = 'capture-2';
        home.capture.ping();
        await tester.pump();
        final placeholder = find.byType(V3LivePlaceholderRow);
        expect(find.descendant(of: placeholder, matching: listening), findsOneWidget);
        expectOrder([today, placeholder, processing, call]);

        home.liveId = 'live-2';
        home.liveTitle = '';
        home.liveOpen = true;
        await home.conversationsV3.refresh();
        await tester.pump();
        final serverLive = find.byKey(const ValueKey('live-2'));
        expect(home.conversationsV3.finishRow, same(pending));
        expect(placeholder, findsNothing);
        expect(find.descendant(of: serverLive, matching: listening), findsOneWidget);
        expectOrder([today, serverLive, processing, call]);
        await shoot(tester, '001-mobile-ios-v3-listening-above-processing');
        await _dispose(tester, home);
      });
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('a manual Finish 404 clears the Home filter and hands Processing off to its result', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        final v3 = home.conversationsV3;
        home.conversations
          ..showShortConversations = true
          ..showDiscardedConversations = true
          ..toggleStarredFilter();
        final pending = OptimisticProcessingPlaceholder.conversation(targetConversationId: 'live-1');
        v3.startManualFinish(pending, null, captureId: home.capture.activeRecordingId);
        expect(v3.settleManualFinish(pending, null, alreadyClosed: true), isTrue);
        await tester.pump();
        expect(find.byKey(const Key('home_processing_row')), findsNothing);
        presentFinishOutcome(
          tester.element(find.byType(ConversationsPage)),
          const FinishAwaitingResult(),
          entry: FinishEntry.home,
        );
        await tester.pump();
        expect(home.conversations.showShortConversations, isTrue);
        expect(home.conversations.showDiscardedConversations, isTrue);
        expect(home.conversations.showsDefaultHome, isFalse);
        expect(find.text('Launch checklist'), findsNothing);
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        expect(find.byType(V3LivePlaceholderRow), findsNothing);
        final processing = find.byKey(const Key('home_processing_row'));
        final navigator = Navigator.of(tester.element(processing));
        await tester.tap(processing);
        await tester.pump();
        expect(navigator.canPop(), isFalse, reason: 'the placeholder has no result page yet');
        home.liveOpen = false;
        await v3.refresh();
        final reads = home.conversations.listReads;
        await tester.pump(const Duration(minutes: 3));
        v3.tick();
        await tester.pump();
        expect(home.conversations.listReads, greaterThan(reads));
        expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
        await shoot(tester, '001-mobile-ios-finish-404-processing');

        home.conversations
          ..showShortConversations = false
          ..showDiscardedConversations = false;
        home.conversations.upsertConversation(
          _conversation('live-1', home.liveStart, 'Launch checklist',
              v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.writing)),
          preserveHomeStep: false,
        );
        await tester.pump();
        await tester.pump();
        expect(find.byKey(const Key('home_processing_row')), findsNothing);
        expect(find.text('Launch checklist'), findsOneWidget);
        expect(v3.finishRow, isNull);
        expect(find.byType(V3LivePlaceholderRow), findsNothing);
        await shoot(tester, '002-mobile-ios-v3-manual-finish-summary');

        home.capture.activeRecordingId = 'capture-2';
        home.capture.ping();
        await tester.pump();
        expect(find.byType(V3LivePlaceholderRow), findsOneWidget,
            reason: 'the next capture can show Listening before its live window exists');
        await _dispose(tester, home);
        debugDefaultTargetPlatformOverride = null;
      });
    });

    for (final (caseName, image) in [
      ('failed summary', '003-mobile-ios-v3-manual-finish-failed'),
      ('legacy failed projection', null),
      ('hidden result', '001-mobile-ios-hidden-finish'),
      ('20-minute deadline', '002-mobile-ios-finish-deadline'),
      ('20-minute deadline off Home', null),
      ('20-minute deadline followed by a result', null),
    ]) {
      testWidgets('a $caseName settles the manual finish and stops list polling', (tester) async {
        await withClock(Clock.fixed(_now), () async {
          debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
          final palette = OmiColors.active;
          addTearDown(() => OmiColors.active = palette);
          OmiColors.active = OmiColors.forBrightness(Brightness.dark);
          final home =
              await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
          final v3 = home.conversationsV3;
          final recording = home.conversations.conversations.firstWhere((row) => row.id == 'rec-1');
          home.conversations.conversations.removeWhere((row) =>
              row.v3?.tileState == ConversationTileState.transcribing ||
              row.v3?.tileState == ConversationTileState.writing);
          home.conversations.groupConversationsByDate();
          final pending = OptimisticProcessingPlaceholder.conversation(targetConversationId: recording.id);
          v3.startManualFinish(pending, recording.id, captureId: home.capture.activeRecordingId);
          expect(v3.settleManualFinish(pending, recording), isTrue);
          home.liveOpen = false;
          await v3.refresh();
          await tester.pump();
          expect(find.byKey(const Key('home_processing_row')), findsOneWidget,
              reason: 'the unrelated failed conversation must not settle this finish');

          final resultAfterTimeout = caseName == '20-minute deadline followed by a result';
          int? forcedBefore;
          if (caseName.startsWith('20-minute deadline')) {
            await tester.pump(const Duration(minutes: 19, seconds: 59));
            expect(v3.finishRow, same(pending));
            forcedBefore = home.conversations.forcedReads;
            expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
            if (caseName == '20-minute deadline off Home' || resultAfterTimeout) {
              final tabs = tester.element(find.byType(ConversationsPage)).read<HomeProvider>();
              tabs.setIndex(HomeProvider.tasksTab);
              await tester.pump(const Duration(seconds: 1));
              expect(v3.finishRow, isNull);
              expect(find.byType(SnackBar), findsNothing);
              if (resultAfterTimeout) {
                home.conversations.upsertConversation(
                  _conversation('live-1', home.liveStart, 'Launch checklist', v3: _done),
                  preserveHomeStep: false,
                );
                await tester.pump();
              }
              tabs.setIndex(HomeProvider.homeTab);
            } else {
              await tester.pump(const Duration(seconds: 1));
            }
          } else if (caseName == 'legacy failed projection') {
            home.conversations.upsertConversation(
              _conversation('live-1', home.liveStart, 'Launch checklist', status: ConversationStatus.processing)
                  .withHomeStep('failed'),
              preserveHomeStep: false,
            );
          } else {
            home.conversations.upsertConversation(
              _conversation('live-1', home.liveStart, 'Launch checklist',
                  v3: ConversationV3Fields(
                      kind: caseName == 'hidden result' ? 'media' : 'conversation',
                      homeHidden: caseName == 'hidden result',
                      tileState:
                          caseName == 'hidden result' ? ConversationTileState.done : ConversationTileState.failed,
                      recordingIds: const ['rec-1'])),
            );
          }
          await tester.pump();
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 300));
          expect(v3.finishRow, isNull);
          expect(find.byKey(const Key('home_processing_row')), findsNothing);
          expect(find.byType(SnackBar), findsNothing);
          expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
          expect(find.byKey(const Key('conversation_summary_failed_indicator')), findsNothing);
          expect(find.text('Launch checklist'), resultAfterTimeout ? findsOneWidget : findsNothing);
          if (forcedBefore != null) {
            expect(home.conversations.forcedReads, forcedBefore + 1, reason: 'the deadline reconciles the list once');
          }
          if (image != null) await shoot(tester, image);

          await tester.pump(const Duration(minutes: 3));
          final reads = home.conversations.listReads;
          v3.tick();
          await tester.pump();
          expect(home.conversations.listReads, reads);
          await _dispose(tester, home);
          debugDefaultTargetPlatformOverride = null;
        });
      });
    }

    testWidgets('visible Summary opens its first live recap', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() {
          OmiColors.active = palette;
          debugDefaultTargetPlatformOverride = null;
          LiveSummarySection.debugStream = null;
        });
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        home.detailSegments = recapSpeech;
        final events = StreamController<SummaryStreamEvent>();
        var opens = 0;
        LiveSummarySection.debugStream = (_) {
          opens++;
          return events.stream;
        };
        await tester.tap(find.text('Launch checklist'));
        await settleDetailTab(tester);
        expect(opens, 0);
        await tester.tap(find.text('Summary'));
        await settleDetailTab(tester);
        expect(opens, 1);
        await shoot(tester, '007-mobile-ios-v3-summary-opens-recap');
        events.add(SummaryDone(
          Structured('Launch checklist', 'The team confirmed Thursday’s launch. Sam will send the final checklist.'),
          _now.subtract(const Duration(minutes: 9)),
        ));
        await settleDetailTab(tester);
        expect(find.textContaining('The team confirmed Thursday’s launch.'), findsOneWidget);
        expect(find.textContaining('Summary through'), findsOneWidget);
        await shoot(tester, '008-mobile-ios-v3-summary-live-recap');
        await _dispose(tester, home);
        debugDefaultTargetPlatformOverride = null;
        unawaited(events.close());
      });
    });

    testWidgets('Home, and opening the conversation in progress', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        var summaryOpens = 0;
        final sections = StreamController<SummaryStreamEvent>();
        LiveSummarySection.debugStream = (_) {
          summaryOpens++;
          return sections.stream;
        };
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        expect(find.byKey(const Key('live_conversation_end')), findsNothing);
        await shoot(tester, '001-mobile-ios-v3-home-live-row');

        await tester.tap(find.text('Launch checklist'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(ConversationDetailPage), findsOneWidget);
        _expectLiveDetail(tester);
        await shoot(tester, '002-mobile-ios-v3-live-detail-end');

        // Opening Summary shows the available recent transcript without a model write.
        await tester.tap(find.text('Summary'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byKey(const Key('live_summary_in_progress')), findsOneWidget);
        expect(find.text('Recent transcript'), findsOneWidget);
        expect(find.byKey(const Key('live_summary_recent_transcript')), findsOneWidget);
        expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
        expect(find.text('Writing your summary…'), findsNothing);
        expect(find.byKey(const Key('live_summary_open_transcript')), findsNothing);
        expect(summaryOpens, 0, reason: 'a conversation still in progress has no summary to write yet');
        await shoot(tester, '006-mobile-ios-v3-live-detail-summary-tab');

        // The ⋯ menu offers nothing that writes, edits, shares or deletes an unfinished conversation.
        await tester.tap(find.byKey(const Key('conversation_more')));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.text('Search'), findsOneWidget);
        for (final hidden in ['Reprocess Conversation', 'Summary Template', 'Copy Summary', 'Share Audio', 'Delete']) {
          expect(find.text(hidden), findsNothing, reason: '$hidden waits until the conversation ends');
        }
        await tester.tapAt(const Offset(20, 700));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));

        await tester.tap(find.byKey(const Key('live_conversation_end')));
        await tester.pump();
        expect(home.capture.endCalls, 1, reason: "the pendant double-tap's action");
        expect(find.byKey(const Key('live_conversation_end')), findsNothing,
            reason: 'nothing is left on this phone to end');

        LiveSummarySection.debugStream = null;
        unawaited(sections.close());
        await tester.pageBack();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));

        // Between windows the live row's placeholder holds the place, not the pendant capture card.
        home.capture.segments = [
          TranscriptSegment(
              id: 's2',
              text: 'Next item.',
              speaker: 'SPEAKER_00',
              isUser: true,
              personId: null,
              start: 0,
              end: 2,
              translations: []),
        ];
        home.liveOpen = false;
        await home.conversationsV3.refresh();
        await tester.pump();
        await tester.pump();
        expect(find.byType(V3LivePlaceholderRow), findsOneWidget);
        await shoot(tester, '003-mobile-ios-v3-home-live-placeholder');

        debugDefaultTargetPlatformOverride = null;
        await _dispose(tester, home);
      });
    });

    testWidgets('the live row in Today: placeholder, its page, untitled, then titled', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));

        // Streaming with neither a local transcript nor a server window: the placeholder leads Today.
        home.capture
          ..segments = []
          ..verifiedLiveServerRecordingId = 'rec-1';
        home.liveOpen = false;
        await home.conversationsV3.refresh();
        await tester.pump();
        await tester.pump();
        expect(find.byType(V3LivePlaceholderRow), findsOneWidget);
        expect(visibleHomeFinish, findsNothing);
        await shoot(tester, '009-mobile-ios-v3-placeholder-in-today');

        // Its page reads Listening until the server names the conversation.
        await tester.tap(find.byType(V3LivePlaceholderRow));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.descendant(of: find.byKey(const Key('live_page_v3_title')), matching: find.text('Listening')),
            findsOneWidget);
        expect(finishButton.hitTestable(), findsOneWidget);
        await shoot(tester, '002-mobile-ios-placeholder-page-finish');
        await tester.pageBack();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));

        // The server window opens untitled: same slot, "Listening" over "Live · 11m", no date.
        home.liveTitle = '';
        home.liveOpen = true;
        await home.conversationsV3.refresh();
        await tester.pump();
        await tester.pump();
        expect(find.byType(V3LivePlaceholderRow), findsNothing);
        expect(find.descendant(of: find.byKey(const ValueKey('live-1')), matching: find.text('Listening')),
            findsOneWidget);
        await shoot(tester, '011-mobile-ios-v3-live-row-untitled');

        // Named: the real title, same slot.
        home.liveTitle = 'Launch checklist';
        await home.conversationsV3.refresh();
        await tester.pump();
        await tester.pump();
        expect(find.descendant(of: find.byKey(const ValueKey('live-1')), matching: find.text('Launch checklist')),
            findsOneWidget);
        await shoot(tester, '012-mobile-ios-v3-live-row-titled');
        debugDefaultTargetPlatformOverride = null;
        await _dispose(tester, home);
      });
    });

    testWidgets('Home, light', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.light);
        final home = await _pumpHome(tester,
            v3: true, boundary: boundary, theme: theme(Brightness.light), size: const Size(393, 852));
        await shoot(tester, '004-mobile-ios-v3-home-light');

        await tester.tap(find.text('Launch checklist'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.pump(const Duration(milliseconds: 500));
        _expectLiveDetail(tester);
        await shoot(tester, '005-mobile-ios-v3-live-detail-light');
        debugDefaultTargetPlatformOverride = null;
        await _dispose(tester, home);
      });
    });
  });
}

/// The live conversation's page as it opens: on its transcript, a live chip with the speech so far,
/// no Share, and End beside Ask Omi.
void _expectLiveDetail(WidgetTester tester) {
  expect(find.textContaining('Deposit is due Friday', findRichText: true), findsWidgets,
      reason: 'it opens on the transcript');
  expect(find.byKey(const Key('conversation_when_live')), findsOneWidget);
  expect(find.text('Live · 11m'), findsOneWidget, reason: "the speech so far, the length its Home row shows");
  expect(find.byKey(const Key('conversation_share')), findsNothing, reason: 'nothing to share until it ends');
  expect(find.byKey(const Key('conversation_star')), findsOneWidget);
  expect(find.byKey(const Key('live_conversation_end')), findsOneWidget);
}

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}
