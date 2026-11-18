import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

// Nik, 2026-11-18 (TestFlight 1.0.593, pendant, v3): Finish on the live page did nothing and went
// back to the list; the conversation showed up 4 minutes later. A batch pendant's page shows only
// the on-device preview, never `segments`, so Finish took the "nothing heard" branch. Finish must
// process it and open the conversation itself, in a processing state until the server has it.

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
  Future<void> finalizeCurrentSession() async {}
}

class _Syncs {
  final phone = _PhoneSync();
}

class _Wal implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// The on-device preview as the live page reads it: its lines and its running word count.
class _Preview extends ChangeNotifier implements LivePreviewController {
  _Preview(this.lines, this.totalWordsSeen);

  @override
  final List<LivePreviewLine> lines;

  @override
  final int totalWordsSeen;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends CaptureProvider {
  _Capture({this.preview, this.closed, this.answer})
      : super(
          walService: _Wal(),
          connectivity: CaptureConnectivityBoundary(
            initiallyConnected: true,
            changes: const Stream.empty(),
            isConnected: () => true,
          ),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  final LivePreviewController? preview;
  final ({String id, DateTime at, int previewWords})? closed;
  final CreateConversationResponse? answer;
  var finishes = 0;

  /// The page renders the preview; this fake only answers what Finish reads, so it is handed over
  /// at the tap.
  bool tapped = false;

  @override
  LivePreviewController? get livePreview => tapped ? preview : null;

  @override
  ({String id, DateTime at, int previewWords})? get lastServerClose => closed;

  @override
  String? get liveCaptureSource => 'omi';

  @override
  Future<CreateConversationResponse?> finishCaptureWithResult() async {
    finishes++;
    return answer;
  }
}

Map<String, dynamic> _row(String id, {String createdAt = '2026-11-18T22:00:09Z', Map<String, dynamic>? extra}) => {
      'id': id,
      'created_at': createdAt,
      'started_at': createdAt,
      'finished_at': '2026-11-18T22:19:35Z',
      'source': 'omi',
      'status': 'completed',
      'structured': {'title': 'Fundraising call', 'overview': 'A synthetic summary', 'emoji': '📞'},
      'transcript_segments': [
        {'text': 'Synthetic speech.', 'start': 0.0, 'end': 4.0, 'is_user': true}
      ],
      ...?extra,
    };

ServerConversation _conversation(String id, {String createdAt = '2026-11-18T22:00:09Z', Map<String, dynamic>? extra}) =>
    ServerConversation.fromJson(_row(id, createdAt: createdAt, extra: extra));

ServerConversation _derived(String id, String recordingId, {String createdAt = '2026-11-18T22:00:09Z'}) =>
    _conversation(id, createdAt: createdAt, extra: {
      'kind': 'conversation',
      'tile_state': 'writing',
      'recording_pieces': [
        {'recording_id': recordingId, 'audio_file_id': 'a1', 'start': 0.0, 'end': 600.0}
      ],
    });

ServerConversation _recordingDoc(String id) => _conversation(id, extra: {
      'recording': true,
      'status': 'processing',
      'structured': {'title': ''}
    });

const _line = LivePreviewLine(id: 'l1', text: 'We closed the round', isFinal: true);

class _Harness {
  _Harness(this.home, this.capture);
  final HomeProvider home;
  final _Capture capture;
}

Future<_Harness> _pump(WidgetTester tester, _Capture capture) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final home = HomeProvider()..setIndex(HomeProvider.tasksTab);
  final device = _StubDeviceProvider();
  final connectivity = _StubConnectivityProvider();
  final usage = UsageProvider();
  addTearDown(home.dispose);
  addTearDown(capture.dispose);
  addTearDown(device.dispose);
  addTearDown(connectivity.dispose);
  addTearDown(usage.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
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
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => const LiveEpisodePage()),
                ),
                child: const Text('home'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('home'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  expect(find.byType(LiveEpisodePage), findsOneWidget);
  return _Harness(home, capture);
}

/// Records the page Finish replaced the live page with, without building it.
Future<Widget?> _finishAndCapturePushed(WidgetTester tester, _Capture capture) async {
  final dynamic state = tester.state(find.byType(LiveEpisodePage));
  capture.tapped = true;
  await (state.debugStopConversation(capture) as Future<void>);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  // The replacement is built on the next frame; read the route's page before the test tears down.
  final finished = find.byType(FinishedCapturePage);
  if (finished.evaluate().isNotEmpty) return tester.widget(finished);
  return null;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a batch pendant Finish with only preview lines processes the capture', (tester) async {
    final harness = await _pump(
      tester,
      _Capture(
          preview: _Preview(const [_line], 4),
          answer: CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1'))),
    );

    final page = await _finishAndCapturePushed(tester, harness.capture) as FinishedCapturePage?;

    expect(harness.capture.finishes, 1, reason: 'the preview is what this page shows; it is something to process');
    expect(harness.home.selectedIndex, HomeProvider.homeTab);
    expect(page?.recordingId, 'rec-1', reason: 'v3 answers with the recording; wait for its conversation');
    expect(find.byKey(const Key('finished_capture_processing')), findsOneWidget);
    expect(find.text('Processing'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(LiveEpisodePage), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  test('the conversation Process Now returns opens its own page; a recording waits; none goes Home', () {
    final page = finishedCapturePageFor(_conversation('c-1'));
    expect(page, isA<ConversationDetailPage>());
    expect((page as ConversationDetailPage).conversation.id, 'c-1');
    expect((finishedCapturePageFor(_recordingDoc('rec-1')) as FinishedCapturePage).recordingId, 'rec-1');
    expect(finishedCapturePageFor(null), isNull);
    expect(finishedCapturePageFor(_conversation('c-2', extra: {'discarded': true})), isNull);
  });

  testWidgets('Finish right after the server closed the recording opens that one', (tester) async {
    final harness = await _pump(
      tester,
      _Capture(
        preview: _Preview(const [_line], 4),
        closed: (id: 'rec-closed', at: DateTime.now().subtract(const Duration(seconds: 3)), previewWords: 4),
      ),
    );

    final page = await _finishAndCapturePushed(tester, harness.capture) as FinishedCapturePage?;

    expect(harness.capture.finishes, 0, reason: 'nothing was heard since; the new recording is empty');
    expect(page?.recordingId, 'rec-closed');
    expect(harness.home.selectedIndex, HomeProvider.homeTab);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('with nothing heard, Finish says so and returns to the page it came from', (tester) async {
    final harness = await _pump(tester, _Capture(preview: _Preview(const [], 0)));

    final dynamic state = tester.state(find.byType(LiveEpisodePage));
    harness.capture.tapped = true;
    await (state.debugStopConversation(harness.capture) as Future<void>);
    await tester.pump();

    expect(harness.capture.finishes, 0);
    expect(find.text('Nothing to process yet.'), findsWidgets);
    expect(harness.home.selectedIndex, HomeProvider.tasksTab);
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(LiveEpisodePage), findsNothing);
    await tester.pump(const Duration(seconds: 5));
  });

  group('FinishedCapturePage', () {
    test('matches the derived conversation, never the recording or an unrelated sync copy', () {
      final rows = [
        _conversation('3d2eea45-sync-piece'), // #25728: same span, no piece of the recording
        _recordingDoc('rec-1'),
        _derived('714c4186', 'rec-1'),
        _derived('other', 'rec-2'),
      ];
      expect(FinishedCapturePage.match(rows, 'rec-1')?.id, '714c4186');
      expect(FinishedCapturePage.match(rows, 'rec-3'), isNull);
    });

    test('of several conversations from one recording it opens the newest, the top Home row', () {
      final rows = [
        _derived('first', 'rec-1', createdAt: '2026-11-18T22:00:09Z'),
        _derived('second', 'rec-1', createdAt: '2026-11-18T22:12:00Z'),
      ];
      expect(FinishedCapturePage.match(rows, 'rec-1')?.id, 'second');
    });

    test('before v3 the conversation is matched by its own id', () {
      expect(FinishedCapturePage.match([_conversation('c-1')], 'c-1')?.id, 'c-1');
    });

    testWidgets('waits, then opens the conversation as soon as it is listed', (tester) async {
      var reads = 0;
      ServerConversation? opened;
      await tester.pumpWidget(MaterialApp(
        locale: const Locale('en'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: FinishedCapturePage(
          recordingId: 'rec-1',
          fetch: () async => ++reads < 3 ? [_conversation('3d2eea45-sync-piece')] : [_derived('714c4186', 'rec-1')],
          open: (_, conversation) => opened = conversation,
        ),
      ));
      await tester.pump();
      expect(find.text('Processing'), findsOneWidget);
      expect(find.text('The summary will appear once the transcript is ready.'), findsOneWidget);
      expect(opened, isNull);

      await tester.pump(const Duration(seconds: 5));
      expect(opened, isNull);
      await tester.pump(const Duration(seconds: 5));
      expect(opened?.id, '714c4186');
      final readsWhenOpened = reads;
      await tester.pump(const Duration(seconds: 15));
      expect(reads, readsWhenOpened, reason: 'polling stops once it opened');
      await tester.pumpWidget(const SizedBox());
    });
  });
}
