import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/episodes/finished_capture_page.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/finish_outcome.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

// ux-contract §17 Outcomes, audit 2026-11-19 (C1, C4, C5, C6, C7, C9): every Finish ends in
// something the reader can see. For each capture source (pendant streaming, pendant batch, phone
// mic) and each answer (success, server refuses, no answer, exception, discarded) this pins what is
// on screen. Before the fix a failed Finish cleared the transcript and popped to Home in silence.

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

class _Preview extends ChangeNotifier implements LivePreviewController {
  _Preview(this.lines, this.totalWordsSeen);

  @override
  final List<LivePreviewLine> lines;

  @override
  int totalWordsSeen;

  @override
  int get sessionGeneration => 1;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

enum _Source { pendantStreaming, pendantBatch, phone }

/// What Process Now answers, or how it fails.
sealed class _Answer {
  const _Answer();
}

class _Replies extends _Answer {
  const _Replies(this.outcome);
  final InProgressProcessOutcome outcome;
}

class _Throws extends _Answer {
  const _Throws();
}

/// The real CaptureProvider with Process Now faked. Like the controller, Finish moves the capture's
/// lines aside before the server answers (and the phone recording stops).
class _Capture extends CaptureProvider {
  _Capture(this.source, this.answer)
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
        ) {
    if (source != _Source.pendantBatch) segments = [_segment('s1', 'We closed the round at forty')];
  }

  final _Source source;
  _Answer answer;
  final preview = _Preview(const [LivePreviewLine(id: 'l1', text: 'We closed the round', isFinal: true)], 4);
  var finishes = 0;
  bool _phoneLive = true;

  @override
  LivePreviewController? get livePreview => source == _Source.pendantBatch ? preview : null;

  @override
  bool get localPreviewAdmitted => false;

  @override
  String? get liveCaptureSource => switch (source) {
        _Source.phone => _phoneLive ? 'phone' : null,
        _ => 'omi',
      };

  @override
  void noteClientFinish() => lastClientFinish = (at: DateTime.now(), previewWords: 4, previewSession: 1);

  @override
  Future<InProgressProcessOutcome> finishCaptureWithOutcome() async {
    finishes++;
    segments = [];
    _phoneLive = false;
    notifyListeners();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    return switch (answer) {
      _Replies(:final outcome) => outcome,
      _Throws() => throw StateError('socket closed underneath'),
    };
  }
}

TranscriptSegment _segment(String id, String text) => TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_00',
      isUser: true,
      personId: null,
      start: 0,
      end: 3,
      translations: const [],
    );

ServerConversation _conversation(String id, {Map<String, dynamic>? extra}) => ServerConversation.fromJson({
      'id': id,
      'created_at': '2026-11-19T10:00:00Z',
      'started_at': '2026-11-19T10:00:00Z',
      'finished_at': '2026-11-19T10:10:00Z',
      'source': 'omi',
      'status': 'completed',
      'structured': {'title': 'Fundraising call', 'overview': 'A synthetic summary', 'emoji': '📞'},
      'transcript_segments': const [],
      ...?extra,
    });

ServerConversation _recordingDoc(String id, {bool notProcessed = false}) => _conversation(id, extra: {
      'recording': true,
      'status': notProcessed ? 'in_progress' : 'processing',
      'structured': {'title': ''},
    });

_Answer _success() => _Replies(InProgressProcessOutcome(
    response: CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1'))));
_Answer _refused() => _Replies(InProgressProcessOutcome(
    response:
        CreateConversationResponse(messages: const [], conversation: _recordingDoc('rec-1', notProcessed: true))));
const _Answer _noAnswer = _Replies(InProgressProcessOutcome(absence: ProcessAbsence.transport));
_Answer _discarded() => _Replies(InProgressProcessOutcome(
    response: CreateConversationResponse(messages: const [], conversation: null), absence: ProcessAbsence.emptyBody));

Future<HomeProvider> _pump(WidgetTester tester, _Capture capture) async {
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
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const LiveEpisodePage())),
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
  return home;
}

Future<void> _tapFinish(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('process_now_button')));
  await tester.pump();
  // The transcript stays while the server has not answered (C7).
  await tester.pump(const Duration(milliseconds: 20));
  await tester.pump(const Duration(milliseconds: 400));
}

void _expectTranscriptKept(_Capture capture) {
  if (capture.source == _Source.pendantBatch) return; // its page shows preview lines, never cleared
  expect(find.textContaining('We closed the round at forty', findRichText: true), findsWidgets,
      reason: 'the reader still sees what they made after the request that could fail');
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  for (final source in _Source.values) {
    group(source.name, () {
      testWidgets('success opens the processing page, never Home', (tester) async {
        final capture = _Capture(source, _success());
        final home = await _pump(tester, capture);
        await _tapFinish(tester);

        expect(capture.finishes, 1);
        expect(find.byType(FinishedCapturePage), findsOneWidget);
        expect(find.byKey(const Key('finished_capture_processing')), findsOneWidget);
        expect(home.selectedIndex, HomeProvider.homeTab, reason: 'Back lands on Home, where it will be');
        await tester.pumpWidget(const SizedBox());
      });

      testWidgets('no answer keeps the transcript on the live page with Try Again, which sends it again',
          (tester) async {
        final capture = _Capture(source, _noAnswer);
        await _pump(tester, capture);
        _expectTranscriptKept(capture); // the finder sees the transcript before the tap
        await _tapFinish(tester);

        expect(find.byType(LiveEpisodePage), findsOneWidget, reason: 'never a silent pop to Home (C1)');
        expect(find.text("Didn't go through. Your audio is safe."), findsOneWidget);
        expect(find.text('Try Again'), findsOneWidget);
        expect(find.byKey(const Key('process_now_button')), findsOneWidget, reason: 'Finish stays (C7)');
        _expectTranscriptKept(capture);

        capture.answer = _success();
        await tester.tap(find.text('Try Again'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 20));
        await tester.pump(const Duration(milliseconds: 400));
        expect(capture.finishes, 2, reason: 'Try Again re-sends even with the lines moved aside (C4)');
        expect(find.byType(FinishedCapturePage), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      });

      testWidgets('an exception keeps the page and the transcript; the next Finish sends again', (tester) async {
        final capture = _Capture(source, const _Throws());
        await _pump(tester, capture);
        await _tapFinish(tester);

        expect(find.byType(LiveEpisodePage), findsOneWidget);
        expect(find.text("Didn't go through. Your audio is safe."), findsOneWidget);
        expect(find.text('Nothing new yet.'), findsNothing);
        _expectTranscriptKept(capture);

        capture.answer = _success();
        await _tapFinish(tester);
        expect(capture.finishes, 2, reason: 'not "Nothing to process yet" (C4)');
        expect(find.byType(FinishedCapturePage), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      });

      testWidgets('a server that has none of it yet says so and keeps the page', (tester) async {
        final capture = _Capture(source, _refused());
        await _pump(tester, capture);
        await _tapFinish(tester);

        expect(find.byType(LiveEpisodePage), findsOneWidget);
        expect(find.text("Audio's still on its way."), findsOneWidget);
        expect(find.text('Nothing new yet.'), findsNothing, reason: 'the page shows words (C5)');
        _expectTranscriptKept(capture);
        await tester.pumpWidget(const SizedBox());
      });

      testWidgets('a discarded recording says it was too short or empty, then returns', (tester) async {
        final capture = _Capture(source, _discarded());
        await _pump(tester, capture);
        await _tapFinish(tester);

        expect(find.text('That recording was too short or empty to keep.'), findsOneWidget);
        expect(find.text('Nothing new yet.'), findsNothing);
        await tester.pump(const Duration(seconds: 1));
        expect(find.byType(LiveEpisodePage), findsNothing);
        expect(find.byType(FinishedCapturePage), findsNothing, reason: 'nothing to wait 20 minutes for (C6)');
        await tester.pump(const Duration(seconds: 5));
      });
    });
  }

  test('every Process Now answer maps to one outcome; none is a bare null', () {
    InProgressProcessOutcome reply(ServerConversation? c, [ProcessAbsence? absence]) => InProgressProcessOutcome(
        response: c == null ? null : CreateConversationResponse(messages: const [], conversation: c), absence: absence);
    FinishOutcome of(InProgressProcessOutcome o, {bool heard = true}) =>
        FinishOutcome.fromProcess(o, heardSomething: heard);

    expect((of(reply(_conversation('c-1'))) as FinishOpened).conversation.id, 'c-1');
    expect((of(reply(_recordingDoc('rec-1'))) as FinishProcessing).recordingId, 'rec-1');
    expect(of(reply(_recordingDoc('rec-1', notProcessed: true))), isA<FinishNotReceived>());
    expect(of(reply(_recordingDoc('rec-1', notProcessed: true)), heard: false), isA<FinishNothingNew>());
    expect(of(reply(_conversation('c-2', extra: {'discarded': true}))), isA<FinishDiscarded>());
    expect(of(reply(null, ProcessAbsence.emptyBody)), isA<FinishDiscarded>());
    expect((of(reply(null, ProcessAbsence.notFound)) as FinishNothingNew).alreadySaved, isTrue);
    expect((of(reply(null, ProcessAbsence.transport)) as FinishFailed).reason, FinishFailure.noAnswer);
    expect((of(reply(null)) as FinishFailed).reason, FinishFailure.noAnswer);
  });
}
