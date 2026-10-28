import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/conversations.dart' show parseHiddenNoiseCounts;
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
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
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

import '../helpers/sfpro_font_fixtures.dart';

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

/// Home groups by the real clock, so the render's day is today.
DateTime _today(int h, int m) {
  final n = DateTime.now();
  return DateTime(n.year, n.month, n.day, h, m);
}

final _seedNow = _today(23, 40);

ServerConversation _conversation(int i) => _day[i % _day.length].build(i);

ServerConversation _titled(String id, String title, String emoji, DateTime at, Duration length, {bool noise = false}) =>
    ServerConversation(
      discarded: noise,
      contentKind: noise ? 'noise' : 'conversation',
      id: id,
      speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0]),
      createdAt: at,
      startedAt: at,
      finishedAt: at.add(length),
      structured: Structured(title, 'Overview.', emoji: emoji, category: 'other'),
      transcriptSegments: const [],
    );

class _Row {
  const _Row(this.title, this.emoji, this.h, this.m, this.length);
  final String title;
  final String emoji;
  final int h;
  final int m;
  final Duration length;
  ServerConversation build(int i) => _titled('conv-$i', title, emoji, _today(h, m), length);
}

const _day = [
  _Row("Is that why it's funny?", '🧠', 23, 34, Duration(minutes: 3, seconds: 31)),
  _Row('Cooking dinner and discussing team meetings', '🍲', 19, 36, Duration(minutes: 54)),
  _Row('Blue Board and Adapter Troubleshooting', '🔧', 19, 23, Duration(minutes: 7)),
  _Row('Omi TestFlight Feedback and Home Controls', '📱', 17, 36, Duration(hours: 1)),
  _Row('On-device preview UX and episode screens', '📱', 15, 20, Duration(minutes: 38)),
  _Row('Mercury Account and Breakfast Stop', '☕', 10, 37, Duration(minutes: 14)),
];

final _folded = [
  _titled('noise-1', 'Are any of these learnings applicable for…', '💬', _today(15, 7), const Duration(seconds: 2),
      noise: true),
  _titled('noise-2', 'ừ', '💬', _today(15, 3), const Duration(minutes: 1, seconds: 49), noise: true),
  _titled('noise-3', 'Mm-', '💬', _today(14, 59), const Duration(minutes: 1, seconds: 8), noise: true),
  _titled('noise-4', 'I only listen to That part.', '💬', _today(11, 48), const Duration(seconds: 61), noise: true),
];

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

/// Home with a live episode, a realistic day of conversations, and that day's folded noise clips.
class _Home {
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
      for (var i = 0; i < _day.length; i++) _conversation(i),
    ]
    ..groupConversationsByDate()
    ..foldedNoiseCounts = {_today(0, 0): _folded.length}
    // The list endpoint returns every discarded row; only noise/media fold.
    ..foldedNoiseRowsFetcherOverride = ((start, end) async => [
          ..._folded,
          _titled('manual', 'Discarded by hand', '💬', _today(9, 0), const Duration(minutes: 3))..discarded = true,
        ])
    ..conversationDetailsFetcherOverride = (id) async => hydrated(int.parse(id.substring('conv-'.length)));

  /// The detail endpoint's copy: the same conversation with every line.
  ServerConversation hydrated(int i) => _conversation(i);
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
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.light),
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

const _out = String.fromEnvironment('OMI_NOISE_FOLD_RENDER_DIR');

Future<void> _shoot(WidgetTester tester, String name, {required bool reveal, required double height}) async {
  tester.view.physicalSize = Size(390, height);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.runAsync(_loadFonts);
  final home = _Home();
  if (reveal) {
    home.conversations.foldedNoiseByDate[_today(0, 0)] = _folded;
    home.conversations.revealedNoiseDates.add(_today(0, 0));
  }
  const boundary = Key('render');
  await tester.pumpWidget(RepaintBoundary(key: boundary, child: _app(home)));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
  expect(find.byKey(ValueKey('noise_fold_${_today(0, 0).toIso8601String()}')), findsOneWidget);
  _paintProductFont(tester.renderObject<RenderRepaintBoundary>(find.byKey(boundary)));
  await tester.pump();
  if (_out.isEmpty) return;
  await tester.runAsync(() async {
    final image = await tester.renderObject<RenderRepaintBoundary>(find.byKey(boundary)).toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_out).create(recursive: true);
    await File('$_out/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    AnalyticsManager.configure(_RecordingAdapter());
    await AnalyticsManager.init();
  });
  tearDown(() {
    AnalyticsManager.resetForTesting();
    VisibilityDetectorController.instance.updateInterval = const Duration(milliseconds: 500);
  });
  test('counts parse into local days; zero and malformed days drop', () {
    expect(
        parseHiddenNoiseCounts({
          'days': [
            {'date': '2026-10-26', 'count': 2},
            {'date': '2026-10-27', 'count': 5},
            {'date': '2026-10-25', 'count': 0},
            {'date': 7, 'count': 1},
          ],
        }),
        {DateTime(2026, 10, 26): 2, DateTime(2026, 10, 27): 5});
    expect(parseHiddenNoiseCounts(null), isEmpty);
  });

  test('a failed count read keeps the shown counts; show-discarded folds nothing', () async {
    final provider = ConversationProvider(isSignedIn: () => false)
      ..conversations = [_day.first.build(0)]
      ..groupConversationsByDate()
      ..foldedNoiseCounts = {_today(0, 0): 3};
    DateTime? asked;
    provider.hiddenNoiseCountsFetcherOverride = (start, end) async {
      asked = start;
      return null;
    };
    await provider.refreshFoldedNoiseCounts();
    expect(asked, _today(0, 0));
    expect(provider.foldedNoiseCounts, {_today(0, 0): 3});
    provider.showDiscardedConversations = true;
    await provider.refreshFoldedNoiseCounts();
    expect(provider.foldedNoiseCounts, isEmpty);
  });

  test('sign-out forgets the fold, and a reply for the old account is dropped', () async {
    final provider = ConversationProvider(isSignedIn: () => false)
      ..conversations = [_day.first.build(0)]
      ..groupConversationsByDate();
    final reply = Completer<Map<DateTime, int>?>();
    provider.hiddenNoiseCountsFetcherOverride = (start, end) => reply.future;
    final pending = provider.refreshFoldedNoiseCounts();
    provider
      ..foldedNoiseByDate[_today(0, 0)] = _folded
      ..revealedNoiseDates.add(_today(0, 0))
      ..clearUserData();
    reply.complete({_today(0, 0): 4});
    await pending;
    expect(provider.foldedNoiseCounts, isEmpty);
    expect(provider.foldedNoiseByDate, isEmpty);
    expect(provider.revealedNoiseDates, isEmpty);
  });

  test('a clip deleted on this phone leaves its day\'s fold', () {
    final provider = ConversationProvider(isSignedIn: () => false)
      ..foldedNoiseCounts = {_today(0, 0): 4}
      ..foldedNoiseByDate[_today(0, 0)] = List.of(_folded);
    provider.dropFromFoldedNoise('noise-2');
    expect(provider.foldedNoiseCounts, {_today(0, 0): 3});
    expect(provider.foldedNoiseByDate[_today(0, 0)]!.map((c) => c.id), isNot(contains('noise-2')));
  });

  testWidgets('show discarded lists everything and folds nothing', (tester) async {
    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final home = _Home();
    home.conversations
      ..showDiscardedConversations = true
      ..foldedNoiseByDate[_today(0, 0)] = _folded
      ..revealedNoiseDates.add(_today(0, 0));
    await tester.pumpWidget(_app(home));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(ValueKey('noise_fold_${_today(0, 0).toIso8601String()}')), findsNothing);
    expect(find.text('Mm-'), findsNothing, reason: 'no folded rows merge into a show-discarded list');
  });

  testWidgets('folded', (tester) => _shoot(tester, '1-folded', reveal: false, height: 844));
  testWidgets('revealed', (tester) => _shoot(tester, '2-revealed', reveal: true, height: 1120));

  testWidgets('the fold hides the day\'s clips, reveals them in time order, and folds them back', (tester) async {
    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final home = _Home();
    await tester.pumpWidget(_app(home));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    final fold = find.byKey(ValueKey('noise_fold_${_today(0, 0).toIso8601String()}'));
    expect(find.text('Mm-'), findsNothing, reason: 'folded clips never draw a row');
    expect(find.text('4 short clips hidden · Show'), findsOneWidget);
    expect(tester.getSize(fold).height, greaterThanOrEqualTo(44));

    await tester.tap(fold);
    await tester.pump();
    await tester.pump();
    expect(find.text('Mm-'), findsOneWidget);
    expect(find.text('Discarded by hand'), findsNothing, reason: 'only noise/media clips fold');
    expect(find.text('Hide 4 short clips'), findsOneWidget);
    // A revealed clip takes its place in the day: 2:59 PM sits between 3:20 PM and 10:37 AM.
    final mm = tester.getTopLeft(find.text('Mm-')).dy;
    expect(mm, greaterThan(tester.getTopLeft(find.text('On-device preview UX and episode screens')).dy));
    expect(mm, lessThan(tester.getTopLeft(find.text('Mercury Account and Breakfast Stop')).dy));

    await tester.tap(fold);
    await tester.pump();
    expect(find.text('Mm-'), findsNothing);
    expect(find.text('4 short clips hidden · Show'), findsOneWidget);
  });
}

Future<void> _loadFonts() async {
  final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
  for (final entry in fonts) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List<dynamic>) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in const [
    'Roboto',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'FlutterTest',
    'SF Pro Display',
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
  // Evidence only: SF Pro lacks CJK glyphs. Use the host's CJK face without
  // adding a licensed system font to the app bundle or repository.
  final cjk = File('/System/Library/Fonts/Hiragino Sans GB.ttc');
  if (cjk.existsSync()) {
    await (FontLoader('PreviewCjkEvidence')..addFont(Future.value(ByteData.sublistView(await cjk.readAsBytes()))))
        .load();
  }
  final emoji = File('/System/Library/Fonts/Apple Color Emoji.ttc');
  if (emoji.existsSync()) {
    await (FontLoader('PreviewEmoji')..addFont(Future.value(ByteData.sublistView(await emoji.readAsBytes())))).load();
  }
  final icons = _materialIcons();
  if (icons != null) {
    final bytes = await icons.readAsBytes();
    await (FontLoader('MaterialIcons')..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(bytes))))).load();
  }
}

/// Repaints every paragraph in the SF Pro fixture, so text styled with a family
/// the test engine lacks does not render as boxes in the evidence.
void _paintProductFont(RenderObject object) {
  if (object is RenderParagraph) object.text = _productFont(object.text);
  object.visitChildren(_paintProductFont);
  object.markNeedsPaint();
}

InlineSpan _productFont(InlineSpan span) {
  if (span is! TextSpan) return span;
  final style = span.style ?? const TextStyle();
  final family = style.fontFamily;
  if (family != null && (family.startsWith('packages/') || family.contains('Icons'))) return span;
  return TextSpan(
    text: span.text,
    style:
        style.copyWith(fontFamily: 'SF Pro Display', fontFamilyFallback: const ['PreviewEmoji', 'PreviewCjkEvidence']),
    children: span.children?.map<InlineSpan>(_productFont).toList(),
    recognizer: span.recognizer,
    semanticsLabel: span.semanticsLabel,
    locale: span.locale,
  );
}

File? _materialIcons() {
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10; i++) {
    for (final path in ['artifacts/material_fonts', 'material_fonts']) {
      final candidate = File('${dir.path}/$path/MaterialIcons-Regular.otf');
      if (candidate.existsSync()) return candidate;
    }
    if (dir.path == dir.parent.path) break;
    dir = dir.parent;
  }
  return null;
}
