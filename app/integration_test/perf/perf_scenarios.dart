import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/services/services.dart';
import 'package:omi/env/env.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/episodes_wire.g.dart' as episode_wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/schema/action_item.dart' show ActionItemsResponse;
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/home/widgets/home_tab_switcher.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/dev_controls/addressability_catalog.dart' show OmiKeys;
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import '../journeys/support/fixture_backend.dart';
import '../journeys/support/hermetic_boot.dart';
import 'perf_mutations.dart';
import 'production_shell.dart';

const scenarioNames = [
  'home_scroll',
  'detail_scroll',
  'memory_scroll',
  'chat_tap',
  'home_live_scroll',
  'episode_page',
  'device_page',
  'tab_switch',
];
final seedDate = DateTime.utc(2026, 9, 16, 9);
int datasetSize(String name, int fallback) {
  final raw = Platform.environment['PERF_$name'] ?? Platform.environment[name];
  final value = raw == null ? fallback : int.tryParse(raw);
  if (value == null || value < 1 || value > 2000) throw ArgumentError('$name must be 1..2000');
  return value;
}

final datasetSizes = {
  'HOME_ITEMS': datasetSize('HOME_ITEMS', 80),
  'DETAIL_MESSAGES': datasetSize('DETAIL_MESSAGES', 100),
  'MEMORY_ITEMS': datasetSize('MEMORY_ITEMS', 60),
  'CHAT_HISTORY': datasetSize('CHAT_HISTORY', 40),
  'LIVE_SEGMENTS': datasetSize('LIVE_SEGMENTS', 600),
};

/// The live conversation an in-progress capture belongs to, and the episode it forms on a
/// server with the episodes overlay on — David's lag report (1.0.571+, episodes on).
const liveConversationId = 'live-conv-0';

Map<String, dynamic> _liveEpisodeWire() => episode_wire.GeneratedEpisode(
      id: 'perf-ep-live',
      status: 'live',
      startedAt: seedDate.subtract(const Duration(minutes: 47)),
      lastActivityAt: seedDate,
      stateUpdatedAt: seedDate,
      title: 'Rollout planning',
      bullets: const ['Capacity review', 'Lane assignments', 'Migration order'],
      conversationIds: const [liveConversationId],
      moments: [
        for (var m = 0; m * 200 < datasetSizes['LIVE_SEGMENTS']! * 8; m++)
          episode_wire.GeneratedEpisodeMoment(
            id: 'perf-moment-$m',
            conversationId: liveConversationId,
            startedAt: seedDate.subtract(Duration(minutes: 47 - m * 3)),
            endedAt: seedDate.subtract(Duration(minutes: 44 - m * 3)),
            startOffset: (m * 200).toDouble(),
            endOffset: (m * 200 + 180).toDouble(),
            heading: 'Moment $m: rollout capacity',
          ),
      ],
      provisionalItems: [
        for (var k = 0; k < 8; k++)
          episode_wire.GeneratedEpisodeProvisionalItem(
            id: 'perf-item-$k',
            text: 'Captured task $k',
            createdAt: seedDate.subtract(Duration(minutes: k + 1)),
            status: 'provisional',
            conversationId: liveConversationId,
            segmentOffset: (k * 500 + 40).toDouble(),
          ),
      ],
    ).toJson();

/// A pendant capture streaming into a live episode; nothing reaches a device. Transcript lines
/// arrive through the production seam ([CaptureProvider.onSegmentReceived]) so every notify,
/// version bump and listener walks the real path.
class HarnessLiveCapture extends CaptureProvider {
  HarnessLiveCapture()
      : super(
          walService: _PerfWalService(),
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _PerfBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  @override
  String? get liveCaptureSource => 'omi';

  @override
  String? get topConversationId => liveConversationId;
}

class _PerfBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _PerfWalService implements IWalService {
  @override
  dynamic getSyncs() => _PerfSyncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// The phone-storage sync view the live surfaces read: nothing in flight, nothing unsynced.
class _PerfSyncs {
  final phone = _PerfPhoneSyncs();
}

class _PerfPhoneSyncs {
  int getInFlightSeconds() => 0;

  List<dynamic> getSessionUnsyncedWals(int start) => const [];

  List<dynamic> getSessionWals(int start) => const [];
}

TranscriptSegment _liveSegment(int i) => TranscriptSegment(
      id: 'live-seg-$i',
      text: 'Live line $i of the rollout planning session: capacity, lanes and migration order.',
      speaker: i % 5 == 0 ? 'SPEAKER_01' : 'SPEAKER_00',
      isUser: i % 5 != 0,
      personId: null,
      translations: [],
      start: i * 8.0,
      end: i * 8.0 + 7,
    );

/// Adds history/pagination only at the external backend seam. All other routes
/// are delegated to the imported journey fixture, including the real SSE reply.
class PerfWorld {
  static bool _servicesCreated = false;
  late JourneyFixtureBackend backend;
  late HttpServer proxy;
  late Directory nativeDirectory;
  final client = HttpClient();
  late ConversationProvider conversations;
  late MemoriesProvider memories;
  final messages = MessageProvider();
  late EpisodeProvider episodes;
  late HarnessLiveCapture capture;
  late DeviceProvider device;

  Future<void> seed() async {
    _liveSegmentCounter = 0;
    mockCommonPlatformChannels();
    nativeDirectory = await Directory.systemTemp.createTemp('omi-perf-native-');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMessageHandler(
      'dev.flutter.pigeon.path_provider_foundation.PathProviderApi.getDirectoryPath',
      (_) async => const StandardMessageCodec().encodeMessage([nativeDirectory.path]),
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/connectivity'),
      (_) async => throw MissingPluginException('Host connectivity probe unavailable'),
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/connectivity_status'),
      (_) async => null,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('com.omi/phone_calls/events'), (call) async => null);
    backend = await JourneyHermeticBoot.start();
    if (!_servicesCreated) {
      // init constructs real services before the unavailable hardware probe.
      // Keep its default connectivity state; loopback HTTP remains real.
      try {
        await ServiceManager.init();
      } on MissingPluginException {
        // Host-only hardware I/O boundary.
      }
      _servicesCreated = true;
    }
    for (var i = 0; i < datasetSizes['HOME_ITEMS']!; i++) {
      backend.conversations.add(ServerConversation(
        id: 'perf-conv-$i',
        createdAt: seedDate.subtract(Duration(minutes: i)),
        structured:
            Structured('Performance conversation $i', 'Deterministic summary $i.', emoji: '🧠', category: 'other'),
        transcriptSegments: i == 0
            ? [
                for (var j = 0; j < datasetSizes['DETAIL_MESSAGES']!; j++)
                  TranscriptSegment(
                      id: 'segment-$j',
                      text: 'Deterministic transcript message $j. We discussed the project and its next steps.',
                      speaker: 'SPEAKER_00',
                      isUser: true,
                      personId: null,
                      start: j * 5.0,
                      end: j * 5.0 + 4,
                      translations: [])
              ]
            : [],
      ).toJson());
    }
    for (var i = 0; i < datasetSizes['MEMORY_ITEMS']!; i++) {
      backend.memories.add({
        'id': 'perf-memory-$i',
        'uid': JourneyFixtureBackend.fixtureUid,
        'content': 'Performance memory $i: deterministic project preference and context.',
        'category': 'manual',
        'created_at': seedDate.toIso8601String(),
        'updated_at': seedDate.toIso8601String(),
        'reviewed': true,
        'manually_added': true,
        'visibility': 'private'
      });
    }
    proxy = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    proxy.listen((request) async {
      final path = request.uri.path;
      if (request.method == 'GET' && path == '/v1/apps/search') {
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({
          'data': [],
          'pagination': {'total': 0, 'count': 0, 'offset': 0, 'limit': 50, 'hasNext': false, 'hasPrevious': false},
          'filters': {'sort': 'popular', 'categories': [], 'capabilities': [], 'languages': [], 'deployed_on': []},
        }));
        await request.response.close();
        return;
      }
      // The episodes overlay: the live episode (and its moments/items) behind the real API client.
      if (request.method == 'GET' &&
          (path == '/v1/episodes/live' || path.startsWith('/v1/episodes/by-conversation/'))) {
        final live = path == '/v1/episodes/live' ||
            Uri.decodeComponent(path.substring('/v1/episodes/by-conversation/'.length)) == liveConversationId;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({
          'enabled': true,
          'episode': live ? _liveEpisodeWire() : null,
        }));
        await request.response.close();
        return;
      }
      if (request.method == 'GET' && ['/v2/messages', '/v3/memories', '/v1/conversations'].contains(path)) {
        final List<Map<String, dynamic>> rows;
        if (path == '/v2/messages') {
          rows = [
            for (var i = 0; i < datasetSizes['CHAT_HISTORY']!; i++)
              {
                'id': 'perf-history-$i',
                'created_at': seedDate.subtract(Duration(minutes: i)).toIso8601String(),
                'text': 'Deterministic history message $i',
                'sender': i.isEven ? 'ai' : 'human',
                'type': 'text',
                'from_integration': false,
                'files': [],
                'files_id': [],
                'memories': [],
              }
          ];
        } else {
          rows = path == '/v3/memories' ? backend.memories : backend.conversations;
        }
        final offset = int.tryParse(request.uri.queryParameters['offset'] ?? '') ?? 0;
        final limit = path == '/v2/messages'
            ? rows.length
            : int.tryParse(request.uri.queryParameters['limit'] ?? '') ?? rows.length;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(rows.skip(offset).take(limit).toList()));
        await request.response.close();
        return;
      }
      final upstream = await client.openUrl(request.method, Uri.parse(backend.baseUrl).resolveUri(request.uri));
      request.headers.forEach((name, values) {
        if (name != HttpHeaders.hostHeader && name != HttpHeaders.contentLengthHeader) {
          upstream.headers.set(name, values);
        }
      });
      await upstream.addStream(request);
      final response = await upstream.close();
      request.response.statusCode = response.statusCode;
      response.headers.forEach((name, values) {
        request.response.headers.set(name, values);
      });
      await request.response.addStream(response);
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${proxy.port}/');
    Env.armDebugJourneyCredentialTrust();
    Env.addDebugTrustedAuthority('127.0.0.1');
    conversations = ConversationProvider(isSignedIn: () => true);
    memories = MemoriesProvider();
    episodes = EpisodeProvider(clock: () => seedDate.add(_liveElapsed.value));
    capture = HarnessLiveCapture();
    device = DeviceProvider(clock: () => seedDate, chargingConnectionLoader: (_) async => null);
    await conversations.forceRefreshConversations();
    while (conversations.hasMoreConversations) {
      if (!await conversations.getMoreConversationsFromServer()) break;
    }
    await memories.loadMemories();
    await messages.refreshMessages();
    expect(conversations.conversations.length, datasetSizes['HOME_ITEMS']);
    expect(memories.memories.length, datasetSizes['MEMORY_ITEMS']);
    expect(messages.messages.length, datasetSizes['CHAT_HISTORY']);
    // A capture that has been running for a while: the transcript already on screen, through
    // the production segment seam so every listener and version bump runs.
    final liveCount = datasetSizes['LIVE_SEGMENTS']!;
    for (var batch = 0; batch * 3 < liveCount; batch++) {
      capture.onSegmentReceived([
        for (var j = batch * 3; j < (batch + 1) * 3 && j < liveCount; j++) _liveSegment(j),
      ]);
      await Future<void>.delayed(Duration.zero);
    }
    expect(capture.segments.length, liveCount);
  }

  /// Virtual time the live capture has run for; advanced by scenario scripts so the 1-second
  /// clock and the running length move like a real capture.
  final _liveElapsed = ValueNotifier<Duration>(Duration.zero);

  Future<void> boot(WidgetTester tester, {List<SingleChildWidget> extraProviders = const []}) async {
    await JourneyHermeticBoot.pumpPage(tester,
        page: const Scaffold(),
        appBuilder: (page) => injectPerfMutation(PerfProductionShell(page: page)),
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
          ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
          ChangeNotifierProvider<MessageProvider>.value(value: messages),
          ChangeNotifierProvider(create: (_) => LocalRecordingsProvider()),
          ChangeNotifierProvider(create: (_) => PhoneCallProvider.forTesting()),
          ChangeNotifierProvider<DeviceProvider>.value(value: device),
          ChangeNotifierProvider(create: (_) => SpeakerTagPromptsProvider(now: () => seedDate)),
          ChangeNotifierProvider(create: (_) => CaptureProvider(now: () => seedDate)),
          ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
            create: (_) => ConversationDetailProvider()..selectedDate = conversationLocalDayKey(seedDate),
            update: (_, app, conversations, previous) => previous!..setProviders(app, conversations),
          ),
          ...extraProviders,
        ]);
  }

  Future<void> close() async {
    conversations.dispose();
    memories.dispose();
    messages.dispose();
    episodes.dispose();
    capture.dispose();
    device.dispose();
    _liveElapsed.dispose();
    client.close(force: true);
    await proxy.close(force: true);
    await backend.stop();
    JourneyHermeticBoot.stop();
    await nativeDirectory.delete(recursive: true);
  }
}

/// Advance real fixture transport and then the fake-zone continuations. A single
/// real delay cannot finish multi-step headers/body/SSE work in a fake clock.
Future<void> drainFixtureIo(WidgetTester tester, {int cycles = 5}) async {
  for (var i = 0; i < cycles; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pump();
  }
}

Future<void> pumpFrames(WidgetTester tester, int count) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 16));
  }
}

Future<void> scrollRoundTrip(WidgetTester tester, Type page) async {
  final candidates = find.descendant(
    of: find.byType(page),
    matching: find.byWidgetPredicate(
        (widget) => widget is Scrollable && axisDirectionToAxis(widget.axisDirection) == Axis.vertical),
  );
  final scrollable =
      candidates.evaluate().map((e) => find.byElementPredicate((candidate) => identical(candidate, e))).firstWhere(
            (finder) => tester.state<ScrollableState>(finder).position.maxScrollExtent > 0,
            orElse: () => throw StateError('$page has no vertical scroll extent; '
                '${candidates.evaluate().map((e) => (e as StatefulElement).state).toList()}'),
          );
  final state = tester.state<ScrollableState>(scrollable);
  expect(state.position.maxScrollExtent, greaterThan(0), reason: '$page must contain seeded scroll content');
  for (final direction in [-1.0, 1.0]) {
    for (var n = 0; n < 100; n++) {
      await tester.fling(scrollable, Offset(0, direction * 500), 3000);
      await pumpFrames(tester, 24);
      await drainFixtureIo(tester);
      final pos = state.position;
      if (direction < 0 ? pos.pixels >= pos.maxScrollExtent - 1 : pos.pixels <= pos.minScrollExtent + 1) break;
      if (n == 99) fail('$page did not reach scroll endpoint');
    }
    // iOS bouncing physics may cross the endpoint before returning to rest.
    // Fixed virtual frames keep this deterministic; the collector itself schedules
    // frames, so pumpAndSettle would never finish during the measured window.
    await pumpFrames(tester, 120);
  }
  expect(state.position.pixels, closeTo(state.position.minScrollExtent, 1));
}

/// Providers for the surfaces David's lag report names: episodes on and a live capture
/// streaming (the live row on Home, the live episode page).
List<SingleChildWidget> liveEpisodeProviders(PerfWorld world) => [
      ChangeNotifierProvider<EpisodeProvider>.value(value: world.episodes),
      ChangeNotifierProvider<CaptureProvider>.value(value: world.capture),
    ];

/// The providers a scenario needs beyond the world's own: the live-episode surfaces add the
/// episodes overlay and the streaming capture on top of the world's providers; the device page
/// adds a sync in progress.
List<SingleChildWidget> providersFor(String name, PerfWorld world) => switch (name) {
      'home_live_scroll' || 'episode_page' => liveEpisodeProviders(world),
      'device_page' => [ChangeNotifierProvider<SyncProvider>.value(value: _PerfSyncProvider())],
      _ => const <SingleChildWidget>[],
    };

/// A sync in progress: a device catch-up with WALs still missing, read by the device page
/// through its production selectors.
class _PerfSyncProvider extends ChangeNotifier implements SyncProvider {
  @override
  SyncState get syncState => const SyncState(status: SyncStatus.syncing);
  @override
  bool get isSyncing => true;
  @override
  List<Wal> get allWals => wals;
  final wals = <Wal>[
    for (var i = 0; i < 12; i++)
      Wal(timerStart: 1, codec: BleAudioCodec.opus, seconds: 300, status: WalStatus.miss, storage: WalStorage.sdcard),
  ];
  @override
  int get missingWalsInSeconds => 3600;
  @override
  bool get isRateLimited => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

int _liveSegmentCounter = 0;

/// Delivers transcript lines the way the socket does: a small batch per call, through the
/// production seam. Returns the number delivered so far.
int deliverLiveSegments(PerfWorld world, {int batches = 1, int perBatch = 2}) {
  for (var b = 0; b < batches; b++) {
    final start = _liveSegmentCounter + b * perBatch;
    world.capture.onSegmentReceived([for (var j = 0; j < perBatch; j++) _liveSegment(100000 + start + j)]);
  }
  _liveSegmentCounter += batches * perBatch;
  return _liveSegmentCounter;
}

/// Advances the live capture's virtual clock by one second (the row's clock reads it).
void tickLiveClock(PerfWorld world) {
  world._liveElapsed.value += const Duration(seconds: 1);
}

/// Lets the episodes capability land (Home reads it after the first frame) and the live
/// surface mount: the row appears, its watchers start polling, the dot starts pulsing.
Future<void> settleLiveEpisode(WidgetTester tester, PerfWorld world) async {
  for (var i = 0; i < 5; i++) {
    await pumpFrames(tester, 30);
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 120));
    });
  }
}

/// [liveScrollRoundTripOnKey] over a page type.
Future<void> liveScrollRoundTrip(WidgetTester tester, PerfWorld world, Type page) async {
  final candidates = find.descendant(
    of: find.byType(page),
    matching: find.byWidgetPredicate(
        (widget) => widget is Scrollable && axisDirectionToAxis(widget.axisDirection) == Axis.vertical),
  );
  final scrollable =
      candidates.evaluate().map((e) => find.byElementPredicate((candidate) => identical(candidate, e))).firstWhere(
            (finder) => tester.state<ScrollableState>(finder).position.maxScrollExtent > 0,
            orElse: () => throw StateError('$page has no vertical scroll extent'),
          );
  await _flingBothEnds(tester, world, scrollable, page.toString());
}

/// The four Stage-2 surfaces: Home under a live episode (episodes on, capture streaming, a
/// long Today list), the live episode page, the device page, and Home↔Tasks tab switches.
Future<void> runLiveScenario(WidgetTester tester, PerfWorld world, String name) async {
  switch (name) {
    case 'home_live_scroll':
      // The shell's Scaffold supplies the Material the capture card's ink needs; the first
      // frames still show the card while the episodes capability is in flight.
      globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(
          builder: (_) => Scaffold(
              body: ConversationsPage(
                  requestInitialLoad: false, loadRecaps: () async => (items: <DailySummary>[], ok: true)))));
      await settleLiveEpisode(tester, world);
      expect(find.byKey(const ValueKey('home_live_episode_row')), findsOneWidget,
          reason: 'Home must show the live episode row');
      await liveScrollRoundTrip(tester, world, ConversationsPage);
      globalNavigatorKey.currentState!.pop();
      await drainFixtureIo(tester);
      await pumpFrames(tester, 120);
      expect(find.byType(ConversationsPage), findsNothing);
    case 'episode_page':
      globalNavigatorKey.currentState!
          .push(MaterialPageRoute<void>(builder: (_) => const LiveEpisodePage(topConversationId: liveConversationId)));
      await settleLiveEpisode(tester, world);
      expect(find.byKey(const ValueKey('live_episode_page')), findsOneWidget,
          reason: 'the live episode page must be showing the episode layout');
      // Summary first: it holds the moments, the captured items and the preview.
      await liveScrollRoundTripOnKey(tester, world, const Key('live_episode_summary'));
      // Then the live transcript itself, with lines still arriving.
      final tab = find.descendant(of: find.byType(TabBar), matching: find.byType(Tab)).at(1);
      await tester.tap(tab);
      await pumpFrames(tester, 30);
      await liveScrollRoundTripOnKey(tester, world, const ValueKey('live-transcript-$liveConversationId'));
      globalNavigatorKey.currentState!.pop();
      await drainFixtureIo(tester);
      await pumpFrames(tester, 120);
      expect(find.byType(LiveEpisodePage), findsNothing);
    case 'device_page':
      // The pendant David's report is about: connected, syncing its storage.
      world.device.connectedDevice = BtDevice(
        id: 'AA:AA:AA:AA:AA:01',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -40,
      );
      world.device.isConnected = true;
      globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => const DeviceSettings()));
      await pumpFrames(tester, 120);
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 150));
      });
      await pumpFrames(tester, 10);
      await scrollRoundTrip(tester, DeviceSettings);
      globalNavigatorKey.currentState!.pop();
      await drainFixtureIo(tester);
      await pumpFrames(tester, 120);
      expect(find.byType(DeviceSettings), findsNothing);
    case 'tab_switch':
      globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => _TabShellPage(world: world)));
      await settleLiveEpisode(tester, world);
      for (var i = 0; i < 5; i++) {
        await tester.tap(find.byKey(OmiKeys.homeTabTasks));
        await pumpFrames(tester, 30);
        tickLiveClock(world);
        deliverLiveSegments(world);
        await tester.tap(find.byKey(OmiKeys.homeTabHome));
        await pumpFrames(tester, 30);
        tickLiveClock(world);
        deliverLiveSegments(world);
      }
      globalNavigatorKey.currentState!.pop();
      await drainFixtureIo(tester);
      await pumpFrames(tester, 120);
    default:
      throw ArgumentError(name);
  }
}

/// [liveScrollRoundTrip] for a list addressed by its key (the episode page's tabs are private).
Future<void> liveScrollRoundTripOnKey(WidgetTester tester, PerfWorld world, Key key) async {
  final scope = find.byKey(key);
  final candidates = find.descendant(
    of: scope,
    matching: find.byWidgetPredicate(
        (widget) => widget is Scrollable && axisDirectionToAxis(widget.axisDirection) == Axis.vertical),
  );
  final scrollable =
      candidates.evaluate().map((e) => find.byElementPredicate((candidate) => identical(candidate, e))).firstWhere(
            (finder) => tester.state<ScrollableState>(finder).position.maxScrollExtent > 0,
            orElse: () => throw StateError('$key has no vertical scroll extent'),
          );
  await _flingBothEnds(tester, world, scrollable, key.toString());
}

/// Fling-scrolls to both endpoints, delivering transcript lines and clock ticks while the
/// list moves — the live surface never rests while it scrolls.
Future<void> _flingBothEnds(WidgetTester tester, PerfWorld world, Finder scrollable, String label) async {
  final state = tester.state<ScrollableState>(scrollable);
  for (final direction in [-1.0, 1.0]) {
    for (var n = 0; n < 100; n++) {
      await tester.fling(scrollable, Offset(0, direction * 500), 3000);
      await pumpFrames(tester, 24);
      await drainFixtureIo(tester);
      tickLiveClock(world);
      deliverLiveSegments(world);
      final pos = state.position;
      if (direction < 0 ? pos.pixels >= pos.maxScrollExtent - 1 : pos.pixels <= pos.minScrollExtent + 1) break;
      if (n == 99) fail('$label did not reach scroll endpoint');
    }
    await pumpFrames(tester, 120);
  }
  expect(state.position.pixels, closeTo(state.position.minScrollExtent, 1));
}

/// The Home shell's two tabs with the production switch shape: an [IndexedStack] whose slots
/// stay stable, the unvisited tab constructed on first switch, tickers gated to the selected
/// page, and [HomeTabSwitcher] driving [HomeProvider].
class _TabShellPage extends StatefulWidget {
  const _TabShellPage({required this.world});
  final PerfWorld world;
  @override
  State<_TabShellPage> createState() => _TabShellPageState();
}

class _TabShellPageState extends State<_TabShellPage> {
  final List<Widget?> _pages = List<Widget?>.filled(HomeProvider.tabCount, null);

  @override
  Widget build(BuildContext context) {
    final selected = context.select<HomeProvider, int>((home) => home.selectedIndex);
    _pages[selected] ??= selected == HomeProvider.homeTab
        ? ConversationsPage(requestInitialLoad: false, loadRecaps: () async => (items: <DailySummary>[], ok: true))
        : const ActionItemsPage();
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
            create: (_) => ActionItemsProvider(
                getActionItems: (
                        {limit = 50,
                        offset = 0,
                        completed,
                        conversationId,
                        startDate,
                        endDate,
                        dueStartDate,
                        dueEndDate}) async =>
                    const ActionItemsResponse(actionItems: [], hasMore: false))),
        ChangeNotifierProvider(create: (_) => TaskIntegrationProvider(fetchStatus: () async => null)),
        ChangeNotifierProvider(create: (_) => GoalsProvider(goalsFetcher: () async => [])),
      ],
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Column(
          children: [
            const SizedBox(height: 44),
            HomeTabSwitcher(
              onTabTap: (index, isRepeat) => context.read<HomeProvider>().setIndex(index),
            ),
            Expanded(
              child: IndexedStack(
                index: selected,
                children: [
                  for (var index = 0; index < _pages.length; index++)
                    TickerMode(
                      enabled: index == selected,
                      child: _pages[index] ?? const SizedBox.shrink(),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Future<void> runScenario(WidgetTester tester, PerfWorld world, String name) async {
  if (name == 'home_live_scroll' || name == 'episode_page' || name == 'device_page' || name == 'tab_switch') {
    await runLiveScenario(tester, world, name);
    return;
  }
  final Widget page = switch (name) {
    'home_scroll' =>
      ConversationsPage(requestInitialLoad: false, loadRecaps: () async => (items: <DailySummary>[], ok: true)),
    'detail_scroll' => ConversationDetailPage(
        conversation: world.conversations.conversations.singleWhere((c) => c.id == 'perf-conv-0'),
        initialTab: ConversationTab.transcript),
    'memory_scroll' => const MemoriesPage(showMindMap: false),
    'chat_tap' => const ChatPage(),
    _ => throw ArgumentError(name),
  };
  globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => page));
  // Virtual time must cover the production iOS route transition.
  await pumpFrames(tester, 120);
  // Complete real loopback I/O outside the virtual clock, then fixed UI pumps.
  await tester.runAsync(() async {
    await Future<void>.delayed(const Duration(milliseconds: 100));
  });
  await pumpFrames(tester, 10);
  await drainFixtureIo(tester);
  if (name == 'chat_tap') {
    const prompt = 'Summarize the deterministic performance fixture.';
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), prompt);
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    for (var i = 0; i < 100 && !world.messages.messages.any((m) => m.id.startsWith('srv-reply-')); i++) {
      await drainFixtureIo(tester, cycles: 1);
    }
    await pumpFrames(tester, 60);
    expect(world.backend.countOf('POST', '/v2/messages'), 1);
    expect(find.textContaining(world.backend.assistantReplyText), findsWidgets);
  } else {
    await scrollRoundTrip(tester, page.runtimeType);
  }
  globalNavigatorKey.currentState!.pop();
  await drainFixtureIo(tester);
  await pumpFrames(tester, 120);
  expect(find.byType(page.runtimeType), findsNothing);
}
