import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
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
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

// Reliability experiment instant_live_text, part 3. A phone whose audio goes to the server over the
// listening connection (Android, phone microphone, an iPhone without its own recogniser) shows nothing
// new on the open conversation's page until batch lands. On, that page tells the listening connection
// its transcript is on screen, so the server streams, and the lines it sends back show under the
// transcript until the conversation itself holds them.

const _phone = 'android_06b76a44';
const _listening = 'listening-recording';
final _started = DateTime.utc(2026, 11, 25, 0, 36);

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

/// A capture without the on-phone preview: its lines come from the server over the listening connection.
class _Capture extends CaptureProvider {
  _Capture(this.lines, {this.preview = false})
      : super(
          walService: _Wal(),
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  final List<TranscriptSegment> lines;
  final bool preview;

  @override
  LivePreviewController? get livePreview => null;

  @override
  bool get localPreviewAdmitted => preview;

  @override
  bool get pendantCaptureVerified => true;

  @override
  String? get verifiedLiveServerRecordingId => _listening;

  @override
  String? get liveCaptureSource => 'omi';

  @override
  List<TranscriptSegment> get segments => lines;

  @override
  DateTime? get liveTranscriptStartedAt => _started;
}

TranscriptSegment _segment(String id, String text, double start, double end) =>
    TranscriptSegment.fromJson({'id': id, 'text': text, 'start': start, 'end': end, 'is_user': true});

ServerConversation _open({List<String> sources = const [_listening]}) => ServerConversation.fromJson({
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
      'v3_recording_ids': sources,
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final platformDeviceId = LiveConversationEndButton.ownDeviceId;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true, 'uid': 'owner-1'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    LiveConversationEndButton.ownDeviceId = () => _phone;
    ListenClientState.instance.resetForTest();
  });

  tearDown(() {
    ReliabilityExperiments.overrideForTesting(null);
    LiveConversationEndButton.ownDeviceId = platformDeviceId;
    ListenClientState.instance.resetForTest();
  });

  Future<void> open(WidgetTester tester, {List<String> sources = const [_listening], bool preview = false}) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final row = _open(sources: sources);
    final capture = _Capture([
      _segment('covered', 'Server words.', 0.0, 4.0),
      _segment('new', 'the server streamed this just now', 20.0, 23.0),
    ], preview: preview);
    final v3 = ConversationsV3Provider(
        uid: () => 'owner-1',
        cached: 'owner-1:1',
        fetchLive: () async => ApiSuccess(ConversationsLiveRead(v3: true, conversation: _open(sources: sources))));
    await v3.refresh();
    final conversations = ConversationProvider(isSignedIn: () => false)..conversations = [row];
    final detail = ConversationDetailProvider(fetchConversation: (_) async => _open(sources: sources));
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

  final streamed = find.byKey(const ValueKey('streamed_line_new'));
  final covered = find.byKey(const ValueKey('streamed_line_covered'));
  bool onScreen() => ListenClientState.instance.value.transcriptVisible;

  testWidgets('off: the page reports nothing and shows no streamed lines', (tester) async {
    await open(tester);
    expect(find.textContaining('Server words', findRichText: true), findsWidgets);
    expect(onScreen(), isFalse);
    expect(streamed, findsNothing);
  });

  testWidgets('on: opening the page reports the transcript on screen, and closing it takes that back', (tester) async {
    ReliabilityExperiments.overrideForTesting({'instant_live_text'});
    await open(tester);
    expect(onScreen(), isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(onScreen(), isFalse);
  });

  testWidgets('on: a streamed line shows under the transcript until the conversation holds it', (tester) async {
    ReliabilityExperiments.overrideForTesting({'instant_live_text'});
    await open(tester);
    expect(streamed, findsOneWidget);
    expect(find.text('the server streamed this just now'), findsOneWidget);
    // The conversation already has these seconds from the server.
    expect(covered, findsNothing);
  });

  testWidgets('on: a conversation this phone does not feed reports nothing and shows none', (tester) async {
    ReliabilityExperiments.overrideForTesting({'instant_live_text'});
    await open(tester, sources: const ['another-phones-recording']);
    expect(onScreen(), isFalse);
    expect(streamed, findsNothing);
  });

  testWidgets('on: a phone with its own recogniser reports, but shows its own lines, not streamed ones',
      (tester) async {
    ReliabilityExperiments.overrideForTesting({'instant_live_text'});
    await open(tester, preview: true);
    expect(onScreen(), isTrue);
    expect(streamed, findsNothing);
  });
}
