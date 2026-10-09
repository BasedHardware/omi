import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/enums.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  _StubConnectivityProvider(this.connected);

  final bool connected;

  @override
  bool get isConnected => connected;

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

class _WalService implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Syncs {
  final phone = _PhoneSync();
}

class _QuietCapture extends CaptureProvider {
  _QuietCapture()
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
  bool get pendantCaptureVerified => false;
}

CaptureProvider _hermeticCapture() {
  return CaptureProvider(
    walService: _WalService(),
    connectivity: CaptureConnectivityBoundary(
      initiallyConnected: true,
      changes: const Stream.empty(),
      isConnected: () => true,
    ),
    bleListeners: _NoopBle(),
    inProgressConversationLoader: () async {},
    localSegmentStore: LocalSegmentStore.disabled(),
  );
}

Future<void> _pumpCapturingPage(
  WidgetTester tester, {
  required CaptureProvider capture,
  required ConnectivityProvider connectivity,
  ConversationCapturingPage page = const ConversationCapturingPage(),
  List<Person> people = const [],
}) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final device = _StubDeviceProvider();
  final usage = UsageProvider();
  addTearDown(device.dispose);
  addTearDown(usage.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider(
            create: (_) => PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))..people = people),
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
        home: page,
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('Someone Else waits for the rejection receipt before opening naming', (tester) async {
    final capture = _hermeticCapture();
    addTearDown(capture.dispose);
    capture.segments = [
      TranscriptSegment(
        id: 'seg',
        text: 'hello',
        speaker: 'SPEAKER_0',
        isUser: false,
        personId: null,
        translations: [],
        start: 0,
        end: 6,
      )
    ];
    capture.photos = [ConversationPhoto(id: 'photo', base64: '', createdAt: DateTime(2026))];
    capture.suggestionsBySegmentId['seg'] = SpeakerLabelSuggestionEvent(
      speakerId: 0,
      personId: '',
      personName: 'Maya',
      segmentId: 'seg',
      suggestedPersonId: 'maya',
    );
    final receipt = Completer<ApiResult<ServerConversation>>();
    await _pumpCapturingPage(
      tester,
      capture: capture,
      connectivity: _StubConnectivityProvider(true),
      people: [Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026))],
      page: ConversationCapturingPage(
          topConversationId: 'live', rejectSpeaker: (_, __, ___, {personId, segmentIds}) => receipt.future),
    );
    await tester.tap(find.byKey(const Key('speaker_suggestion_chip')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Someone Else…'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(NameSpeakerBottomSheet), findsNothing);
    receipt.complete(ApiSuccess(ServerConversation(
      id: 'live',
      createdAt: DateTime(2026),
      structured: Structured('Title', 'Summary'),
    )));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(NameSpeakerBottomSheet), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a terminal outage replaces the Listening placeholder, online or not', (tester) async {
    final capture = _hermeticCapture();
    addTearDown(capture.dispose);
    capture.updateRecordingState(RecordingState.record);
    capture.onMessageEventReceived(
      MessageServiceStatusEvent(
        status: 'stt_failed',
        outcome: 'upstream_error',
        provider: 'deepgram',
        retryable: true,
        reason: 'send_failed',
      ),
    );
    expect(capture.terminalTranscriptionFailure, isNotNull);

    // Online: without the terminal failure the empty state promises a
    // transcript; with it, the same page must say why none will appear yet.
    await _pumpCapturingPage(tester, capture: capture, connectivity: _StubConnectivityProvider(true));

    // Twice by design: the app bar names the outage, and the empty state
    // repeats the same sentence instead of the stale Listening placeholder.
    expect(find.textContaining('recording continues on device and will process later'), findsNWidgets(2));
    expect(find.textContaining('a transcript will appear here'), findsNothing);
  });

  testWidgets('quiet unverified pendant retains live page transcript and Pause with a neutral header', (tester) async {
    final capture = _QuietCapture();
    addTearDown(capture.dispose);
    capture.segments = [
      TranscriptSegment(
          id: 'quiet-segment',
          text: 'Keep this transcript.',
          speaker: 'SPEAKER_0',
          isUser: true,
          personId: null,
          start: 0,
          end: 3,
          translations: []),
    ];
    await _pumpCapturingPage(tester, capture: capture, connectivity: _StubConnectivityProvider(true));
    expect(find.textContaining('Keep this transcript.', findRichText: true), findsOneWidget);
    expect(find.byKey(const Key('capture_pause_button')), findsOneWidget);
    expect(find.textContaining('Listening'), findsNothing);
    expect(find.text('Pendant'), findsOneWidget);
    await tester.pump(const Duration(minutes: 1));
    expect(find.textContaining('Keep this transcript.', findRichText: true), findsOneWidget);
    expect(find.byKey(const Key('capture_pause_button')), findsOneWidget);
    expect(find.textContaining('Listening'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a healthy session keeps the Listening placeholder', (tester) async {
    final capture = _hermeticCapture();
    addTearDown(capture.dispose);
    capture.updateRecordingState(RecordingState.record);

    await _pumpCapturingPage(tester, capture: capture, connectivity: _StubConnectivityProvider(true));

    expect(find.textContaining('a transcript will appear here'), findsOneWidget);
    expect(find.textContaining('recording continues on device'), findsNothing);
  });
}
