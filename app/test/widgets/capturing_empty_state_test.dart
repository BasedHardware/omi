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
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/constants.dart';

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
  @override
  bool get pendantReconnectInFlight => false;
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
  LiveEpisodePage page = const LiveEpisodePage(),
  List<Person> people = const [],
  UsageProvider? usage,
}) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final device = _StubDeviceProvider();
  final ownsUsage = usage == null;
  final effectiveUsage = usage ?? UsageProvider();
  addTearDown(device.dispose);
  if (ownsUsage) addTearDown(effectiveUsage.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider(
            create: (_) => PeopleProvider(loadPeople: () async => PeopleListResponse(people: people))..people = people),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: effectiveUsage),
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

  for (final withPhotos in [false, true]) {
    for (final source in ['manual', 'carried', 'auto']) {
      testWidgets('$source live label (photos: $withPhotos) opens the existing speaker assignment sheet',
          (tester) async {
        final capture = _hermeticCapture();
        addTearDown(capture.dispose);
        capture.segments = [
          TranscriptSegment(
            id: 'label',
            text: 'hello',
            speaker: 'SPEAKER_0',
            isUser: false,
            personId: 'maya',
            translations: [],
            start: 0,
            end: 6,
            speakerLabelSource: source,
          ),
        ];
        if (withPhotos) capture.photos = [ConversationPhoto(id: 'photo', base64: '', createdAt: DateTime(2026))];
        await _pumpCapturingPage(
          tester,
          capture: capture,
          connectivity: _StubConnectivityProvider(true),
          people: [Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026))],
        );
        final label = find.byKey(const ValueKey('edit_speaker_label_label'));
        expect(label, findsOneWidget);
        expect(tester.getSize(label).height, greaterThanOrEqualTo(44));
        expect(find.byKey(Key(source == 'auto' ? 'speaker_label_likely' : 'speaker_label_confirmed')), findsOneWidget);
        await tester.tap(label);
        await tester.pump(const Duration(milliseconds: 300));
        expect(find.byType(NameSpeakerBottomSheet), findsOneWidget);
        final sheet = tester.widget<NameSpeakerBottomSheet>(find.byType(NameSpeakerBottomSheet));
        expect(sheet.speakerId, 0);
        expect(sheet.segmentId, 'label');
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }

  for (final withPhotos in [false, true]) {
    for (final isUser in [false, true]) {
      for (final source in ['auto', 'manual', 'carried']) {
        testWidgets('protected speaker (owner: $isUser, photos: $withPhotos, source: $source) has no edit label',
            (tester) async {
          final capture = _hermeticCapture();
          addTearDown(capture.dispose);
          capture.segments = [
            TranscriptSegment(
              id: 'protected',
              text: 'Keep this line.',
              speaker: 'SPEAKER_${isUser ? 0 : omiSpeakerId}',
              isUser: isUser,
              personId: null,
              translations: [],
              start: 0,
              end: 6,
              speakerLabelSource: source,
            ),
          ];
          if (withPhotos) capture.photos = [ConversationPhoto(id: 'photo', base64: '', createdAt: DateTime(2026))];
          await _pumpCapturingPage(tester, capture: capture, connectivity: _StubConnectivityProvider(true));
          expect(find.byKey(const ValueKey('edit_speaker_label_protected')), findsNothing);
          expect(find.text('Keep this line.', findRichText: true), findsOneWidget);
          if (withPhotos || !isUser) expect(find.text(isUser ? 'You' : 'Omi'), findsOneWidget);
          expect(find.byKey(const Key('speaker_label_likely')), findsNothing);
          expect(find.byKey(const Key('speaker_label_confirmed')), findsNothing);
          await tester.pumpWidget(const SizedBox.shrink());
        });
      }
    }
  }

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
      page: LiveEpisodePage(
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

  testWidgets('a terminal outage states itself once: short app bar, truthful placeholder', (tester) async {
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
    // transcript; with it, the placeholder must not promise one — the banner
    // owns the full statement, and no wedge is declared here.
    await _pumpCapturingPage(tester, capture: capture, connectivity: _StubConnectivityProvider(true));

    expect(find.textContaining('recording continues on device and will process later'), findsOneWidget,
        reason: 'the empty state keeps the one truthful unavailable line');
    expect(find.textContaining('Not transcribing'), findsOneWidget, reason: 'the app bar keeps the short state name');
    expect(find.textContaining('a transcript will appear here'), findsNothing,
        reason: 'no transcript can appear while the outage is known');
  });

  testWidgets('an out-of-credits session never promises a transcript', (tester) async {
    final capture = _hermeticCapture();
    addTearDown(capture.dispose);
    capture.updateRecordingState(RecordingState.record);

    // A metered plan with its transcription minutes spent: the provider itself
    // computes isOutOfCredits from the seeded subscription, no network.
    final usage = UsageProvider(
        subscriptionRequest: () async => UserSubscriptionResponse(
              subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
              transcriptionSecondsUsed: 300,
              transcriptionSecondsLimit: 300,
              wordsTranscribedUsed: 0,
              wordsTranscribedLimit: 0,
              insightsGainedUsed: 0,
              insightsGainedLimit: 0,
            ));
    addTearDown(usage.dispose);
    await usage.fetchSubscription();
    expect(usage.isOutOfCredits, isTrue);

    await _pumpCapturingPage(
      tester,
      capture: capture,
      connectivity: _StubConnectivityProvider(true),
      usage: usage,
    );

    expect(find.textContaining('a transcript will appear here'), findsNothing,
        reason: 'an exhausted plan cannot produce the promised transcript');
    expect(find.textContaining('Transcription is unavailable'), findsOneWidget,
        reason: 'the empty state says why, truthfully');
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
