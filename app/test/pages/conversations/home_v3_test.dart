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
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/live_summary_section.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/conversations/widgets/day_summary_link.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
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
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart' show Wal;
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/ui/ui.dart';

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

final _now = DateTime(2026, 11, 16, 12, 30);

ServerConversation _conversation(String id, DateTime start, String title,
        {ConversationV3Fields? v3, Duration length = const Duration(minutes: 25)}) =>
    ServerConversation(
      id: id,
      speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0]),
      createdAt: start,
      startedAt: start,
      finishedAt: v3?.tileState == ConversationTileState.live ? null : start.add(length),
      structured: Structured(title, 'Overview of $title.', emoji: '💬', category: 'work'),
      transcriptSegments: const [],
      v3: v3,
    );

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

  /// False once the conversation in progress has closed.
  bool liveOpen = true;
  final sync = _StubSyncProvider();
  late final _LiveCapture capture = _LiveCapture();
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
      return ApiSuccess(ConversationsLiveRead(
        v3: v3,
        conversation: v3 && liveOpen
            ? _conversation('live-1', _now.subtract(const Duration(minutes: 20)), 'Launch checklist',
                v3: const ConversationV3Fields(kind: 'conversation', tileState: ConversationTileState.live))
            : null,
      ));
    },
  );
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
      // Its summary failed for good: a warning tile, never the emoji.
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
            create: (_) => ConversationDetailProvider(),
            update: (_, app, conversations, previous) =>
                (previous?..setProviders(app, conversations)) ?? ConversationDetailProvider(),
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

  @override
  Future<bool> fetchConversations({bool restoreMergeWatches = true}) async {
    listReads++;
    return true;
  }
}

List<String> _rowIds(WidgetTester tester) =>
    tester.widgetList<ConversationListItem>(find.byType(ConversationListItem)).map((r) => r.conversation.id).toList();

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
          ['live-1', 'c-call', 'c-transcribing', 'c-writing', 'c-today', 'c-yesterday', 'c-yesterday-2', 'c-failed'],
          reason: 'the live conversation leads Today; the hidden one is only off Home');
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

    testWidgets('Home, and opening the conversation in progress', (tester) async {
      await withClock(Clock.fixed(_now), () async {
        debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
        final palette = OmiColors.active;
        addTearDown(() => OmiColors.active = palette);
        OmiColors.active = OmiColors.forBrightness(Brightness.dark);
        final sections = StreamController<SummaryStreamEvent>();
        LiveSummarySection.debugStream = (_) => sections.stream;
        final home = await _pumpHome(tester, v3: true, boundary: boundary, theme: theme(), size: const Size(393, 852));
        await shoot(tester, '001-mobile-ios-v3-home');

        await tester.tap(find.text('Launch checklist'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(ConversationDetailPage), findsOneWidget);
        expect(find.text('Writing your summary…'), findsOneWidget);
        await shoot(tester, '002-mobile-ios-v3-live-summary-writing');

        sections
          ..add(const SummarySection('## Venue and date\n- The venue holds Thursday the 26th; deposit due Friday.'
              '\n- Capacity is 180 seated, so the guest list needs a cut of about 20.'))
          ..add(const SummarySection('## Run of show\n- Doors at 6, talks at 7, demos after.'
              '\n- You own the slide order; Priya sends speaker bios by Tuesday.'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));
        expect(find.textContaining('deposit due Friday'), findsOneWidget);
        await shoot(tester, '003-mobile-ios-v3-live-summary-streamed');

        LiveSummarySection.debugStream = null;
        unawaited(sections.close());
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
        debugDefaultTargetPlatformOverride = null;
        await _dispose(tester, home);
      });
    });
  });
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
