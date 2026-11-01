import 'package:flutter/material.dart';
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
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/widgets/transcript.dart';

/// Live-episode page notify guards (INV-PERF-1: listeners that run on every notify must be O(1)
/// when nothing relevant changed).
///
/// A live capture notifies several times a minute for as long as it runs — transcript lines, but
/// also metric samples, progress and socket/connection state that change nothing the page shows.
/// These tests pin, with a 600-line transcript and a 24-moment episode:
///
/// * a capture notify that changes nothing the page derives rebuilds none of the page shell
///   (header scaffolding, tabs, running notes, tasks, moments, wrap-up bar) and re-runs none of
///   the per-notify whole-transcript derivations (the membership snapshot copy, the
///   `SpeakerNames` resolver, the moments×segments decoration scan, the photo regroup);
/// * an arriving line rebuilds only what the line changes (the header's participants, the
///   three-line preview, the transcript's own rows) — never the shell around them;
/// * a neighbor provider notify (Device) — which the transcript's own `Consumer2` subscribes to —
///   re-derives nothing.
///
/// Counts are deterministic rebuild/identity counts in the style of
/// `home_after_detail_perf_test.dart`; no wall-clock is measured.

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
  String? get topConversationId => 'c-live';
}

const _conversationId = 'c-live';
final _seedNow = DateTime(2026, 10, 22, 12, 30);

TranscriptSegment _line(int i) => TranscriptSegment(
      id: 'perf-live-$i',
      text: 'Live line $i of the rollout planning session: capacity, lanes and migration order.',
      speaker: i % 5 == 0 ? 'SPEAKER_01' : 'SPEAKER_00',
      isUser: i % 5 != 0,
      personId: null,
      translations: [],
      start: i * 8.0,
      end: i * 8.0 + 7,
    );

/// The episode the lag report is about: long-running, 24 moments across the transcript and 8
/// captured items, so the decoration scan has real work to skip.
Episode _liveEpisode() => Episode(
      id: 'ep-live',
      live: true,
      startedAt: _seedNow.subtract(const Duration(minutes: 48)),
      lastActivityAt: _seedNow,
      title: 'Rollout planning',
      bullets: const ['Capacity first, lanes second', 'Migration order follows the rings'],
      people: const [],
      items: [
        for (var k = 0; k < 8; k++)
          EpisodeItem(
            id: 'item-$k',
            text: 'Captured task $k',
            createdAt: _seedNow.subtract(Duration(minutes: k + 1)),
            conversationId: _conversationId,
            segmentOffset: (k * 500 + 40).toDouble(),
          ),
      ],
      moments: [
        for (var m = 0; m < 24; m++)
          EpisodeMoment(
            id: 'm$m',
            conversationId: _conversationId,
            startedAt: _seedNow.subtract(Duration(minutes: 48 - m * 2)),
            endedAt: _seedNow.subtract(Duration(minutes: 46 - m * 2)),
            startOffset: m * 200.0,
            endOffset: m * 200.0 + 180,
            heading: 'Moment $m',
          ),
      ],
      conversationIds: const [_conversationId],
      stateUpdatedAt: _seedNow,
    );

EpisodeProvider _episodes() {
  final provider = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _liveEpisode())),
    lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    clock: () => _seedNow,
  );
  provider.debugSetLive(_liveEpisode());
  return provider;
}

Future<void> _pump(WidgetTester tester, Widget home,
    {required CaptureProvider capture, required EpisodeProvider episodes, required DeviceProvider device}) async {
  tester.view.physicalSize = const Size(800, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final usage = UsageProvider();
  addTearDown(usage.dispose);
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
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
  await tester.pump(const Duration(milliseconds: 100));
}

Future<void> _unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
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

/// Fires [notify] [times] times, one frame each, and counts how often the live transcript's
/// timeline derivations ran. The snapshot copy, the `SpeakerNames` resolver, the decoration scan
/// and the photo regroup all run in one memoized block, and a fresh `TranscriptWidget.segments`
/// list identity is exactly one run of that block.
Future<int> _notifyCountingDerivations(WidgetTester tester, int times, void Function() notify) async {
  List<TranscriptSegment>? segmentsOf() => tester.widget<TranscriptWidget>(find.byType(TranscriptWidget)).segments;
  var runs = 0;
  var last = segmentsOf();
  for (var i = 0; i < times; i++) {
    notify();
    await tester.pump();
    final now = segmentsOf();
    if (!identical(now, last)) runs++;
    last = now;
  }
  return runs;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('capture notifies that change nothing the page shows rebuild none of the live episode shell',
      (tester) async {
    const seedLines = 600;
    const notifies = 20;
    final capture = _LiveCapture();
    addTearDown(capture.dispose);
    capture.segments = [for (var i = 0; i < seedLines; i++) _line(i)];
    final episodes = _episodes();
    addTearDown(episodes.dispose);
    final device = _StubDeviceProvider();
    addTearDown(device.dispose);
    await _pump(tester, const LiveEpisodePage(), capture: capture, episodes: episodes, device: device);

    expect(find.byKey(const Key('live_episode_page')), findsOneWidget);
    expect(find.text('Rollout planning'), findsOneWidget);
    expect(find.text('Moment 0'), findsOneWidget, reason: 'the summary must show the episode\'s moments');

    // Metric samples, progress and socket-state notifies change nothing the page derives.
    final idle = await _rebuildsDuring(() async {
      for (var i = 0; i < notifies; i++) {
        capture.notifyListeners();
        await tester.pump();
      }
    });
    // Arriving lines: the three-line preview follows the transcript; the shell around it does not.
    final arrivals = await _rebuildsDuring(() async {
      for (var i = 0; i < notifies; i++) {
        capture.onSegmentReceived([_line(2000 + i)]);
        await tester.pump();
      }
    });
    debugPrint('LIVE-PAGE idle-notify rebuilds ($notifies notifies): $idle');
    debugPrint('LIVE-PAGE arrival rebuilds ($notifies lines): $arrivals');

    for (final shellType in [
      'ConversationDetailTabs',
      '_LiveSummaryTab',
      '_SoFarCard',
      '_ItemRow',
      '_MomentRow',
      '_TranscriptPreview',
      'OmiButton',
      'OmiIconButton',
      'LiveTranscriptView',
    ]) {
      expect(idle[shellType] ?? 0, 0,
          reason: 'a capture notify that changes nothing shown must not rebuild $shellType');
    }
    for (final shellType in ['ConversationDetailTabs', '_LiveSummaryTab', '_SoFarCard', '_ItemRow', '_MomentRow']) {
      expect(arrivals[shellType] ?? 0, 0,
          reason: 'an arriving line must not rebuild $shellType: moments, notes and tasks did not change');
    }
    expect(arrivals['_TranscriptPreview'] ?? 0, lessThanOrEqualTo(notifies),
        reason: 'the preview follows the transcript itself');
    expect(capture.segments.length, seedLines + notifies);
    expect(find.text('Rollout planning'), findsOneWidget, reason: 'the page must be unchanged');
    expect(find.textContaining('Live line ${2000 + notifies - 1}', findRichText: true), findsOneWidget,
        reason: 'the newest line must be in the preview');

    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });

  testWidgets('the live transcript re-derives nothing for notifies that do not change it', (tester) async {
    const seedLines = 600;
    const notifies = 20;
    final capture = _LiveCapture();
    addTearDown(capture.dispose);
    capture.segments = [for (var i = 0; i < seedLines; i++) _line(i)];
    final episodes = _episodes();
    addTearDown(episodes.dispose);
    final device = _StubDeviceProvider();
    addTearDown(device.dispose);
    await _pump(tester, const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
        capture: capture, episodes: episodes, device: device);

    expect(find.byType(TranscriptWidget), findsOneWidget);
    // The list follows the newest lines (divider rendering itself is episodes_ui_test's).
    expect(find.textContaining('Live line ${seedLines - 1}'), findsOneWidget,
        reason: 'the seeded transcript must be on screen');

    // Capture notifies that change nothing the transcript shows: no re-copy, no re-name, no
    // decoration re-scan, no photo regroup. A neighbor provider the transcript subscribes to
    // (device state) must re-derive nothing either. An arriving line re-derives at most once per
    // line (its own row), never per frame.
    final idleRuns = await _notifyCountingDerivations(tester, notifies, capture.notifyListeners);
    final deviceRuns = await _notifyCountingDerivations(tester, notifies, device.notifyListeners);
    var nextArrival = 3000;
    final arrivalRuns =
        await _notifyCountingDerivations(tester, notifies, () => capture.onSegmentReceived([_line(nextArrival++)]));
    debugPrint('LIVE-TRANSCRIPT idle-notify derivation runs: $idleRuns/$notifies');
    debugPrint('LIVE-TRANSCRIPT device-notify derivation runs: $deviceRuns/$notifies');
    debugPrint('LIVE-TRANSCRIPT arrival derivation runs: $arrivalRuns/$notifies');

    expect(idleRuns, 0,
        reason: 'a capture notify that changes nothing must not re-derive the timeline '
            '(snapshot copy + SpeakerNames + moments×segments decoration scan + photo regroup)');
    expect(deviceRuns, 0, reason: 'a device notify must not re-derive the timeline: the transcript did not change');
    expect(arrivalRuns, lessThanOrEqualTo(notifies),
        reason: 'an arriving line must cost at most one derivation run, not one per notify');
    expect(capture.segments.length, seedLines + notifies);
    final segments = tester.widget<TranscriptWidget>(find.byType(TranscriptWidget)).segments;
    expect(segments.last.id, 'perf-live-${3000 + notifies - 1}', reason: 'the newest line must have arrived');

    expect(tester.takeException(), isNull);
    await _unmount(tester);
  });
}
