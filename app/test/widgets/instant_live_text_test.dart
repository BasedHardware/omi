import 'package:clock/clock.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/speech_after_end.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

// Reliability experiment instant_live_text. A phone that sends its speech as files waits 40 s to two
// minutes for the server to show the next conversation after an End, and its own recogniser's text was
// hidden for that whole time: Home held the Listening row back, and the open conversation's "Live on
// this phone" lines needed the listening connection's recording to be a source, which it never is here.

const _phone = 'ios_06b76a44';
final _started = DateTime.utc(2026, 11, 25, 0, 36);
final _ended = DateTime.utc(2026, 11, 25, 0, 35, 51);

LivePreviewLine _line(String id, String text,
        {DateTime? startedAt, DateTime? firstSeenAt, List<LivePreviewSpan>? spans}) =>
    LivePreviewLine(
        id: id, text: text, isFinal: false, startedAt: startedAt, firstSeenAt: firstSeenAt, spans: spans ?? const []);

class _Preview extends ChangeNotifier implements LivePreviewController {
  _Preview(this.lines);

  @override
  final List<LivePreviewLine> lines;

  @override
  bool get admitted => true;

  @override
  LivePreviewPhase get phase => LivePreviewPhase.streaming;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Syncs {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Wal implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

/// A pendant capture whose listening connection carries no speech: its recording is empty, and the
/// speech reaches the server as uploaded files.
class _Capture extends CaptureProvider {
  _Capture(this.preview)
      : super(
          walService: _Wal(),
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  final LivePreviewController preview;

  @override
  LivePreviewController? get livePreview => preview;

  @override
  bool get localPreviewAdmitted => true;

  @override
  bool get pendantCaptureVerified => true;

  @override
  String? get verifiedLiveServerRecordingId => 'empty-listening-recording';

  @override
  String? get liveCaptureSource => 'omi';
}

ServerConversation _open({String? device}) => ServerConversation.fromJson({
      'id': 'open',
      'created_at': _started.toIso8601String(),
      'started_at': _started.toIso8601String(),
      'finished_at': _started.add(const Duration(seconds: 4)).toIso8601String(),
      'source': 'omi',
      'status': 'in_progress',
      'structured': {'title': 'Planning', 'overview': '', 'emoji': '🗓️'},
      'transcript_segments': [
        {'id': 's1', 'text': 'Server words.', 'start': 0.0, 'end': 4.0, 'is_user': true},
      ],
      'kind': 'conversation',
      'tile_state': 'live',
      'v3_recording_ids': ['uploaded-1', 'uploaded-2'],
      if (device != null) 'v3_capture_device_id': device,
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final platformDeviceId = LiveConversationEndButton.ownDeviceId;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true, 'uid': 'owner-1'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    LiveConversationEndButton.ownDeviceId = () => _phone;
  });

  tearDown(() {
    ReliabilityExperiments.overrideForTesting(null);
    LiveConversationEndButton.ownDeviceId = platformDeviceId;
  });

  group('words spoken after an End', () {
    test('a line that starts after the End counts; earlier lines and empty ones do not', () {
      final before = _line('a', 'still the old conversation', startedAt: _ended.subtract(const Duration(seconds: 8)));
      expect(SpeechAfterEnd.heard([before], _ended), isFalse);
      expect(
          SpeechAfterEnd.heard([before, _line('b', '   ', startedAt: _ended.add(const Duration(seconds: 2)))], _ended),
          isFalse);
      expect(
          SpeechAfterEnd.heard(
              [before, _line('c', 'new topic', startedAt: _ended.add(const Duration(seconds: 2)))], _ended),
          isTrue);
      expect(SpeechAfterEnd.heard([_line('d', 'new topic', startedAt: _ended)], _ended), isTrue);
    });

    test('a line the speaker carried across the End counts from its first word after it', () {
      LivePreviewSpan word(String text, int seconds) => LivePreviewSpan(
          text: text,
          startedAt: _ended.add(Duration(seconds: seconds)),
          endedAt: _ended.add(Duration(seconds: seconds + 1)));
      final start = _ended.subtract(const Duration(seconds: 3));
      expect(
          SpeechAfterEnd.heard([
            _line('a', 'so that is', startedAt: start, spans: [word('so', -3), word('that', -2)])
          ], _ended),
          isFalse);
      expect(
          SpeechAfterEnd.heard([
            _line('a', 'so that is next', startedAt: start, spans: [word('so', -3), word('next', 1)])
          ], _ended),
          isTrue);
    });

    test('without audio times, the moment the recogniser first reported the line decides', () {
      expect(
          SpeechAfterEnd.heard([_line('a', 'words', firstSeenAt: _ended.subtract(const Duration(seconds: 1)))], _ended),
          isFalse);
      expect(SpeechAfterEnd.heard([_line('a', 'words', firstSeenAt: _ended.add(const Duration(seconds: 1)))], _ended),
          isTrue);
      expect(SpeechAfterEnd.heard([_line('a', 'words')], _ended), isFalse);
    });
  });

  group('the Listening row after an End', () {
    ConversationsV3Provider provider() {
      final v3 = ConversationsV3Provider(
          uid: () => 'owner-1',
          cached: 'owner-1:1',
          fetchLive: () async => const ApiSuccess(ConversationsLiveRead(v3: true, conversation: null)));
      addTearDown(v3.dispose);
      return v3;
    }

    test('an End hides it from the End moment, and speech after it brings it back for good', () {
      withClock(Clock.fixed(_ended), () {
        final v3 = provider();
        var notified = 0;
        v3.addListener(() => notified++);
        expect(v3.listeningSuppressedSince('capture-1'), isNull);
        final pending = OptimisticProcessingPlaceholder.conversation(targetConversationId: 'live-1');
        v3.startManualFinish(pending, null, captureId: 'capture-1');
        expect(v3.suppressListeningAfterFinish('capture-1'), isTrue);
        expect(v3.listeningSuppressedSince('capture-1'), _ended);
        // Another capture is not this End's.
        expect(v3.listeningSuppressedSince('capture-2'), isNull);
        expect(v3.resumeListeningAfterFinish('capture-2'), isFalse);

        final before = notified;
        expect(v3.resumeListeningAfterFinish('capture-1'), isTrue);
        expect(notified, before + 1);
        expect(v3.suppressListeningAfterFinish('capture-1'), isFalse);
        expect(v3.resumeListeningAfterFinish('capture-1'), isFalse);
        // The server accepts the End a few seconds later: the row stays.
        expect(v3.settleManualFinish(pending, null, alreadyClosed: true), isTrue);
        expect(v3.suppressListeningAfterFinish('capture-1'), isFalse);

        // The next End hides it again.
        final next = OptimisticProcessingPlaceholder.conversation(targetConversationId: 'live-2');
        v3.startManualFinish(next, null, captureId: 'capture-1');
        expect(v3.suppressListeningAfterFinish('capture-1'), isTrue);
        expect(v3.settleManualFinish(next, null, alreadyClosed: true), isTrue);
        expect(v3.suppressListeningAfterFinish('capture-1'), isTrue);
      });
    });
  });

  group('the open conversation\'s Live on this phone lines', () {
    Future<void> open(WidgetTester tester, {required String? liveDevice, String liveId = 'open'}) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final row = _open();
      final preview = _Preview([
        _line('old', 'before this conversation', startedAt: _started.subtract(const Duration(seconds: 30))),
        _line('new', 'the phone heard this just now', startedAt: _started.add(const Duration(seconds: 20))),
      ]);
      final capture = _Capture(preview);
      final v3 = ConversationsV3Provider(
          uid: () => 'owner-1',
          cached: 'owner-1:1',
          fetchLive: () async => ApiSuccess(ConversationsLiveRead(
              v3: true,
              conversation: ServerConversation.fromJson({
                ..._open(device: liveDevice).toJson(),
                'id': liveId,
                if (liveDevice != null) 'v3_capture_device_id': liveDevice,
              }))));
      await v3.refresh();
      final conversations = ConversationProvider(isSignedIn: () => false)..conversations = [row];
      final detail = ConversationDetailProvider(fetchConversation: (_) async => _open());
      final apps = AppProvider();
      final home = HomeProvider();
      detail.setProviders(apps, conversations);
      addTearDown(() {
        detail.dispose();
        conversations.dispose();
        apps.dispose();
        capture.dispose();
        v3.dispose();
        home.dispose();
      });
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
            ChangeNotifierProvider<AppProvider>.value(value: apps),
            ChangeNotifierProvider<CaptureProvider>.value(value: capture),
            ChangeNotifierProvider<ConversationsV3Provider>.value(value: v3),
            ChangeNotifierProvider<HomeProvider>.value(value: home),
            ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider(create: (_) => PeopleProvider()),
            ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                fetchStatus: (_) async => null,
                saveStatus: (_, __) async => false,
                deleteStatus: (_) async => false,
                persistPref: (_, __) async {},
              ),
            ),
          ],
          child: ConversationDetailPage(conversation: row, initialTab: ConversationTab.transcript),
        ),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
    }

    final tail = find.byKey(const ValueKey('live_preview_tail_new'));
    final earlier = find.byKey(const ValueKey('live_preview_tail_old'));

    testWidgets('off: a phone whose speech arrives as files sees none', (tester) async {
      await open(tester, liveDevice: _phone);
      expect(find.textContaining('Server words', findRichText: true), findsWidgets);
      expect(tail, findsNothing);
    });

    testWidgets('on: they show under the server text when the latest speech came from this install', (tester) async {
      ReliabilityExperiments.overrideForTesting({'instant_live_text'});
      await open(tester, liveDevice: _phone);
      expect(find.textContaining('Server words', findRichText: true), findsWidgets);
      expect(tail, findsOneWidget);
      expect(find.text('the phone heard this just now'), findsOneWidget);
      // They continue the transcript: no heading over them, and they start at the page's own inset.
      expect(find.byKey(const Key('live_preview_divider')), findsNothing);
      expect(tester.getTopLeft(find.text('the phone heard this just now')).dx, 16.0);
      // Words from before this conversation began belong to the one before it.
      expect(earlier, findsNothing);
    });

    testWidgets('vendor_recognizer_on_opened_app alone shows them by the same fact', (tester) async {
      ReliabilityExperiments.overrideForTesting({'vendor_recognizer_on_opened_app'});
      await open(tester, liveDevice: _phone);
      expect(tail, findsOneWidget);
      expect(find.text('the phone heard this just now'), findsOneWidget);
      expect(earlier, findsNothing);
    });

    testWidgets('on: another install\'s speech, or no device from the server, shows none', (tester) async {
      ReliabilityExperiments.overrideForTesting({'instant_live_text'});
      await open(tester, liveDevice: 'macos_0a1b2c3d');
      expect(tail, findsNothing);
    });

    testWidgets('on: a conversation that is not the account\'s open one shows none', (tester) async {
      ReliabilityExperiments.overrideForTesting({'instant_live_text'});
      await open(tester, liveDevice: _phone, liveId: 'another');
      expect(tail, findsNothing);
    });
  });
}
