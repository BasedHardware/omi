import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/processing_conversations/page.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/media_viewer_page.dart';

import 'native_test_host.dart';

final _l10n = lookupAppLocalizations(const Locale('en'));

class _Device extends ChangeNotifier implements DeviceProvider {
  BtDevice? device;
  @override
  BtDevice? get connectedDevice => device;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  bool connected = true;
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

class _Wal implements IWalService {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Seeded, inert capture state: every mutation the page asks for is recorded, none runs.
class _FakeCapture extends CaptureProvider {
  _FakeCapture()
      : super(
          walService: _Wal(),
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  String? source = 'phone';
  bool paused = false;
  bool callActive = false;
  bool verified = true;
  BtDevice? device;
  int version = 0;
  List<Wal> unsynced = [];
  int inFlight = 0;
  ({int pending, int total}) backlog = (pending: 0, total: 0);
  MessageServiceStatusEvent? transcriptionFailure;
  String? session;
  int finishes = 0;
  Completer<void>? finishGate;
  final assigned = <(int, String, List<String>)>[];
  int walRetries = 0;
  final toggles = <String>[];

  void change(void Function() update) {
    update();
    notifyListeners();
  }

  @override
  String? get liveCaptureSource => source;
  @override
  bool get isPaused => paused;
  @override
  bool get isCallActive => callActive;
  @override
  bool get pendantCaptureVerified => verified;
  @override
  BtDevice? get recordingDevice => device;
  @override
  int get segmentsPhotosVersion => version;
  @override
  List<Wal> get unsyncedSessionWals => unsynced;
  @override
  int get inFlightAudioSeconds => inFlight;
  @override
  ({int pending, int total}) get sessionTranscriptionBacklogCounts => backlog;
  @override
  MessageServiceStatusEvent? get terminalTranscriptionFailure => transcriptionFailure;
  @override
  String? get activeCaptureSessionId => session;
  @override
  String? get topConversationId => 'live-conversation';
  @override
  Future<void> finishCapture() async {
    finishes++;
    await finishGate?.future;
  }

  @override
  Future<bool> assignSpeakerToConversation(int speakerId, String personId, String personName, List<String> segmentIds,
      {bool applyToSpeaker = false}) async {
    assigned.add((speakerId, personId, segmentIds));
    return true;
  }

  @override
  Future<void> retryFailedSessionWalUploads() async => walRetries++;
  @override
  Future<void> pauseCapture() async => toggles.add('pause');
  @override
  Future<void> resumeCapture() async => toggles.add('resume');
}

TranscriptSegment _segment(String id, String text, {int speakerId = 1, bool isUser = false, double start = 0}) =>
    TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_0$speakerId',
      isUser: isUser,
      personId: null,
      start: start,
      end: start + 1,
      translations: [],
    );

ConversationPhoto _photo(String id, DateTime createdAt) => ConversationPhoto(id: id, base64: '', createdAt: createdAt);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  late NativeTestHost host;
  late _FakeCapture capture;
  late _Device device;
  late _Connectivity connectivity;
  late HomeProvider home;

  Future<void> pumpCapture(WidgetTester tester, {void Function(_FakeCapture)? seed}) async {
    host = NativeTestHost.install();
    capture = _FakeCapture();
    seed?.call(capture);
    device = _Device();
    connectivity = _Connectivity();
    home = HomeProvider();
    final usage = UsageProvider();
    final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []))..people = [];
    addTearDown(() {
      capture.dispose();
      device.dispose();
      connectivity.dispose();
      home.dispose();
      usage.dispose();
      people.dispose();
    });
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<PeopleProvider>.value(value: people),
      ],
      child: NativeTestHost.app(const Scaffold(body: Center(child: Text('home')))),
    ));
    unawaited(Navigator.of(tester.element(find.text('home')))
        .push(MaterialPageRoute<void>(builder: (_) => const ConversationCapturingPage())));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(milliseconds: 400));
    await NativeTestHost.settle(tester);
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last);
  List<NativeRow> rows(WidgetTester tester) =>
      IosNativeSurface.debugDispatchRows(tester.state<State<IosNativeSurface>>(find.byType(IosNativeSurface).last));
  NativeRow? row(WidgetTester tester, String id) => rows(tester).where((row) => row.id == id).firstOrNull;
  List<String> section(WidgetTester tester, String id) =>
      surface(tester).sections.firstWhere((section) => section.id == id).rows.map((row) => row.id).toList();

  Future<void> send(WidgetTester tester, String id, [Object? value]) async {
    await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
    await tester.pump();
  }

  testWidgets('the timeline lists photo groups in capture order, then the transcript', (tester) async {
    final start = DateTime(2026, 10, 8, 9);
    await pumpCapture(tester, seed: (capture) {
      capture.segments = [_segment('a', 'First words'), _segment('b', 'Second words', start: 4)];
      capture.photos = [
        _photo('late', start.add(const Duration(minutes: 5))),
        _photo('early', start),
        _photo('early-2', start.add(const Duration(seconds: 10))),
      ];
    });
    expect(find.byType(IosNativeSurface), findsOneWidget);
    expect(section(tester, 'capture_timeline'),
        ['capture_photos:0', 'capture_photos:1', 'capture_segment:0', 'capture_segment:1']);
    expect(row(tester, 'capture_photos:0')!.title, endsWith(_l10n.conversationPhotosCount(2)));
    expect(row(tester, 'capture_photos:0')!.kind, 'navigation');
    expect(row(tester, 'capture_photos:1')!.title, isNot(contains('·')));
    final segment = row(tester, 'capture_segment:1')!;
    expect(segment.kind, 'transcript');
    expect(segment.title, 'Second words');
    expect(segment.subtitle, endsWith('0:04'));
    expect(rows(tester).every((row) => row.valid), true);
    expect(row(tester, 'capture_photos:0')!.imageUri, isNull, reason: 'no photo bytes or thumbnails cross');
  });

  testWidgets('identify opens the existing name-speaker sheet for that segment and speaker', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      capture.segments = [_segment('a', 'Hello', speakerId: 0), _segment('b', 'Hi there', speakerId: 2)];
    });
    expect(row(tester, 'capture_segment:1')!.options.keys, contains('identify'));
    await send(tester, 'capture_segment:1', 'identify');
    await tester.pumpAndSettle();
    final sheet = tester.widget<NameSpeakerBottomSheet>(find.byType(NameSpeakerBottomSheet));
    expect(sheet.segmentId, 'b');
    expect(sheet.speakerId, 2);
  });

  testWidgets('a line whose speaker is being saved is disabled', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      capture.segments = [_segment('a', 'Hello'), _segment('b', 'Saving')];
      capture.taggingSegmentIds = ['b'];
    });
    expect(row(tester, 'capture_segment:0')!.enabled, true);
    expect(row(tester, 'capture_segment:1')!.enabled, false);
    expect(row(tester, 'capture_segment:1')!.projection['enabled'], false);
  });

  testWidgets('Pause follows the classic rules and a call disables it', (tester) async {
    await pumpCapture(tester, seed: (capture) => capture.segments = [_segment('a', 'Hello')]);
    final pause = row(tester, 'capture_pause')!;
    expect(pause.title, _l10n.pause);
    expect(pause.symbol, 'pause.fill');
    await send(tester, 'capture_pause');
    await tester.pump();
    expect(capture.toggles, ['pause']);

    capture.change(() => capture.paused = true);
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_pause')!.title, _l10n.resume);
    expect(row(tester, 'capture_pause')!.symbol, 'play.fill');

    capture.change(() {
      capture.paused = false;
      capture.callActive = true;
    });
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_pause')!.enabled, false);
    expect(row(tester, 'capture_pause')!.title, _l10n.resume);

    // Photo-capture devices keep taking photos: no Pause.
    capture.change(() {
      capture.callActive = false;
      capture.source = 'openglass';
      capture.device = BtDevice(name: 'Glass', id: 'glass', type: DeviceType.openglass, rssi: 0);
    });
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_pause'), isNull);
    expect(row(tester, 'capture_finish'), isNotNull);

    // Nothing recording and nothing captured: neither control.
    capture.change(() {
      capture.source = null;
      capture.segments = [];
    });
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_pause'), isNull);
    expect(row(tester, 'capture_finish'), isNull);
  });

  testWidgets('Finish asks the capture owner once and closes the page', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      capture.segments = [_segment('a', 'Hello')];
      capture.finishGate = Completer<void>();
    });
    home.setIndex(HomeProvider.tasksTab);
    expect(row(tester, 'capture_finish')!.symbol, 'checkmark');
    unawaited(host.sendFromNative(host.created.last, const MethodCall('action', {'id': 'capture_finish'})));
    await tester.pump();
    expect(row(tester, 'capture_finish')!.enabled, false);
    unawaited(host.sendFromNative(host.created.last, const MethodCall('action', {'id': 'capture_finish'})));
    await tester.pump();
    capture.finishGate!.complete();
    await tester.pumpAndSettle();
    expect(capture.finishes, 1);
    expect(find.byType(ConversationCapturingPage), findsNothing);
    expect(home.selectedIndex, HomeProvider.homeTab);
  });

  testWidgets('unsynced audio is named as the classic indicator names it, tappable once when retryable',
      (tester) async {
    final wal = Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 75,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'a.bin');
    await pumpCapture(tester, seed: (capture) => capture.unsynced = [wal]);
    expect(row(tester, 'capture_wal')!.title, _l10n.audioSavedLocally('1m 15s'));
    expect(row(tester, 'capture_wal')!.kind, 'label');
    expect(surface(tester).loading, false);

    wal.retryCount = walMaxAutoRetries;
    capture.change(() {});
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_wal')!.title, _l10n.audioUploadFailedTapRetry('1m 15s'));
    expect(row(tester, 'capture_wal')!.kind, 'button');
    // The indicator itself is the one retry, as on the classic page.
    expect(rows(tester).where((row) => row.id.startsWith('capture_wal')).map((row) => row.id), ['capture_wal']);
    await send(tester, 'capture_wal');
    expect(capture.walRetries, 1);
  });

  testWidgets('uploading audio shows the classic spinner as the surface progress, with its queue', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      capture.inFlight = 20;
      capture.backlog = (pending: 1, total: 3);
    });
    expect(surface(tester).loading, true);
    expect(surface(tester).loadingLabel, _l10n.uploadingAudioForTranscription('20s'));
    expect(row(tester, 'capture_wal'), isNull, reason: 'the progress already carries the text');
    expect(row(tester, 'capture_wal_backlog')!.title, _l10n.transcriptionsPendingFraction(1, 3));

    capture.change(() => capture.inFlight = 0);
    await NativeTestHost.settle(tester);
    expect(surface(tester).loading, false);
    expect(row(tester, 'capture_wal_backlog'), isNull);
  });

  testWidgets('a sentence status is shown in full in the status section under a short title', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      capture.segments = [_segment('a', 'Hello')];
      capture.transcriptionFailure = MessageServiceStatusEvent(status: 'transcription_unavailable');
    });
    expect(surface(tester).title, _l10n.captureSourcePhoneMic);
    expect(section(tester, 'capture_status').first, 'capture_state');
    expect(row(tester, 'capture_state')!.title, _l10n.transcriptionUnavailableRecordingContinues);

    capture.change(() => capture.source = null);
    await NativeTestHost.settle(tester);
    expect(surface(tester).title, _l10n.transcriptionUnavailable);
    expect(row(tester, 'capture_state')!.title, _l10n.transcriptionUnavailableRecordingContinues);

    capture.change(() => capture.transcriptionFailure = null);
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_state'), isNull);
  });

  testWidgets('the empty timeline names what this session can produce', (tester) async {
    await pumpCapture(tester);
    expect(section(tester, 'capture_timeline'), ['capture_empty']);
    expect(row(tester, 'capture_empty')!.title, _l10n.listeningTranscriptWillAppear);
    expect(surface(tester).empty, _l10n.listeningTranscriptWillAppear);

    connectivity
      ..connected = false
      ..notifyListeners();
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_empty')!.title, _l10n.recordingOfflineTranscriptWillCatchUp);

    connectivity.connected = true;
    capture.change(() => capture.verified = false);
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_empty'), isNull, reason: 'an unverified pendant promises nothing');
  });

  testWidgets('the reader follows the newest line and the version, and a drag suspends it', (tester) async {
    await pumpCapture(tester, seed: (capture) => capture.segments = [_segment('a', 'Hello')]);
    var reader = surface(tester).reader!;
    expect(reader.following, true);
    expect(reader.targetId, 'capture_segment:0');
    expect(reader.request, 0);
    expect(reader.scroll!.options.keys, containsAll(['suspend', 'capture_segment:0']));

    capture.change(() {
      capture.segments = [...capture.segments, _segment('b', 'More')];
      capture.version = 3;
    });
    await NativeTestHost.settle(tester);
    reader = surface(tester).reader!;
    expect(reader.targetId, 'capture_segment:1');
    expect(reader.request, 3);

    await send(tester, 'capture_reader_scroll', 'suspend');
    await NativeTestHost.settle(tester);
    expect(surface(tester).reader!.following, false);
    expect(row(tester, 'capture_latest'), isNotNull);

    await send(tester, 'capture_latest');
    await NativeTestHost.settle(tester);
    reader = surface(tester).reader!;
    expect(reader.following, true);
    expect(reader.request, 4);
    expect(row(tester, 'capture_latest'), isNull);

    // A drag suspends following for its own session only: a new session follows again.
    await send(tester, 'capture_reader_scroll', 'suspend');
    await NativeTestHost.settle(tester);
    expect(surface(tester).reader!.following, false);
    capture.change(() => capture.session = 'next-session');
    await NativeTestHost.settle(tester);
    expect(surface(tester).reader!.following, true);
  });

  testWidgets('a pinned suggestion offers the chip answers and Yes labels the speaker', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      capture.segments = [_segment('a', 'Hello', speakerId: 3), _segment('b', 'Again', speakerId: 3)];
      capture.suggestionsBySegmentId = {
        'a': SpeakerLabelSuggestionEvent(
            speakerId: 3, personId: '', personName: '', segmentId: 'a', suggestedPersonId: 'maya'),
      };
    });
    final people = Provider.of<PeopleProvider>(tester.element(find.byType(ConversationCapturingPage)), listen: false);
    people.people = [Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026))];
    people.notifyListeners();
    await NativeTestHost.settle(tester);
    final segment = row(tester, 'capture_segment:0')!;
    expect(segment.options.keys, containsAll(['identify', 'suggestion_accept', 'suggestion_reject']));
    expect(segment.subtitle, contains(_l10n.speakerTagPromptIsThisPerson('Maya')));
    expect(segment.subtitle, contains(_l10n.speakerSuggestionAppliesToSpeaker));
    expect(row(tester, 'capture_segment:1')!.options.keys, isNot(contains('suggestion_accept')));
    await send(tester, 'capture_segment:0', 'suggestion_accept');
    await tester.pump();
    expect(capture.assigned.single.$1, 3);
    expect(capture.assigned.single.$2, 'maya');
    expect(capture.assigned.single.$3, ['a', 'b']);
  });

  testWidgets('a photo group opens the existing media viewer', (tester) async {
    await pumpCapture(tester, seed: (capture) => capture.photos = [_photo('p', DateTime(2026, 10, 8, 9))]);
    await send(tester, 'capture_photos:0');
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(MediaViewerPage), findsOneWidget);
  });

  testWidgets('the carried-speaker note keeps Change and Close', (tester) async {
    await pumpCapture(tester, seed: (capture) {
      final segment = _segment('a', 'Hello')
        ..personId = 'maya'
        ..speakerLabelSource = 'carried';
      capture.segments = [segment];
    });
    final people = Provider.of<PeopleProvider>(tester.element(find.byType(ConversationCapturingPage)), listen: false);
    people.people = [Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026))];
    people.notifyListeners();
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_carried')!.title, _l10n.speakerLabelText('carried', 'Maya'));
    await send(tester, 'capture_carried_close');
    await NativeTestHost.settle(tester);
    expect(row(tester, 'capture_carried'), isNull);
  });

  testWidgets('processing renders natively and keeps the timed-out Try again', (tester) async {
    host = NativeTestHost.install();
    final now = DateTime(2026, 10, 8, 12);
    final conversation = ServerConversation(
      id: 'processing-1',
      createdAt: now.subtract(const Duration(minutes: 10)),
      finishedAt: now.subtract(const Duration(minutes: 5)),
      status: ConversationStatus.processing,
      structured: Structured('', ''),
      transcriptSegments: [_segment('a', 'Words so far')],
    );
    final reprocessed = <String>[];
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(
      value: conversations,
      child: NativeTestHost.app(ProcessingConversationPage(
        conversation: conversation,
        now: () => now,
        reprocess: (id) async {
          reprocessed.add(id);
          return ServerConversation(
              id: id,
              createdAt: conversation.createdAt,
              status: ConversationStatus.completed,
              structured: Structured('Done', ''));
        },
      )),
    ));
    await NativeTestHost.settle(tester);
    expect(surface(tester).title, _l10n.processing);
    expect(surface(tester).loading, true, reason: 'the classic header spins while processing');
    expect(surface(tester).loadingLabel, _l10n.processing);
    expect(section(tester, 'processing_timeline'), ['processing_segment:0']);
    expect(row(tester, 'processing_segment:0')!.title, 'Words so far');
    expect(row(tester, 'processing_timeout')!.title, _l10n.processingTakingLonger);
    await send(tester, 'processing_retry');
    await NativeTestHost.settle(tester);
    expect(reprocessed, ['processing-1']);
    // The reprocess answered with a finished conversation: nothing is stuck, so no second retry.
    expect(row(tester, 'processing_retry'), isNull);
  });

  testWidgets('processing with nothing captured says so', (tester) async {
    host = NativeTestHost.install();
    final conversation = ServerConversation(
        id: 'processing-2',
        createdAt: DateTime(2026, 10, 8),
        status: ConversationStatus.processing,
        structured: Structured('', ''));
    await tester.pumpWidget(NativeTestHost.app(ProcessingConversationPage(conversation: conversation)));
    await NativeTestHost.settle(tester);
    expect(row(tester, 'processing_empty')!.title, _l10n.noContentToDisplay);
    expect(row(tester, 'processing_retry'), isNull);
  });

  testWidgets('the classic processing page keeps the same timed-out Try again', (tester) async {
    final now = DateTime(2026, 10, 8, 12);
    final conversation = ServerConversation(
      id: 'processing-3',
      createdAt: now.subtract(const Duration(minutes: 10)),
      finishedAt: now.subtract(const Duration(minutes: 5)),
      status: ConversationStatus.processing,
      structured: Structured('', ''),
    );
    final reprocessed = <String>[];
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<ConversationProvider>.value(
      value: conversations,
      child: NativeTestHost.app(ProcessingConversationPage(
        conversation: conversation,
        now: () => now,
        reprocess: (id) async {
          reprocessed.add(id);
          return conversation;
        },
      )),
    ));
    await tester.pump();
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.text(_l10n.processingTakingLonger), findsOneWidget);
    await tester.tap(find.byKey(const Key('processing_page_retry_button')));
    await tester.pump();
    expect(reprocessed, ['processing-3']);
  });

  testWidgets('without the native host the live page is the classic page', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final capture = _FakeCapture()..segments = [_segment('a', 'Hello')];
    final device = _Device();
    final connectivity = _Connectivity();
    final usage = UsageProvider();
    addTearDown(() {
      capture.dispose();
      device.dispose();
      connectivity.dispose();
      usage.dispose();
    });
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
      ],
      child: NativeTestHost.app(const ConversationCapturingPage()),
    ));
    await tester.pump();
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.byKey(const Key('process_now_button')), findsOneWidget);
  });

  group('sheets', () {
    Future<List<String>> openSheet(WidgetTester tester, Widget Function(BuildContext, List<String>) sheet) async {
      host = NativeTestHost.install();
      final log = <String>[];
      await tester.pumpWidget(NativeTestHost.app(const Scaffold(body: Center(child: Text('home')))));
      unawaited(Navigator.of(tester.element(find.text('home')))
          .push(MaterialPageRoute<void>(builder: (sheetContext) => Scaffold(body: sheet(sheetContext, log)))));
      await NativeTestHost.settle(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await NativeTestHost.settle(tester);
      return log;
    }

    testWidgets('record options pop the sheet, then run the existing choice', (tester) async {
      final log = await openSheet(
          tester,
          (sheetContext, log) => RecordOptionsSheet(
                nativeTitle: _l10n.recordWith,
                onPickPhoneMic: () {
                  Navigator.pop(sheetContext);
                  log.add('mic');
                },
                onPickPhoneCall: () {
                  Navigator.pop(sheetContext);
                  log.add('call:${ModalRoute.of(sheetContext)!.isCurrent}');
                },
              ));
      expect(surface(tester).title, _l10n.recordWith);
      expect(rows(tester).map((row) => row.id), ['record_options_close', 'record_phone_mic', 'record_phone_call']);
      await send(tester, 'record_phone_call');
      await tester.pumpAndSettle();
      expect(log, ['call:false'], reason: 'the sheet is popped before the choice runs');
      expect(find.byType(RecordOptionsSheet), findsNothing);
    });

    testWidgets('the pendant-is-listening choices pop the sheet, then run the existing choice', (tester) async {
      final log = await openSheet(
          tester,
          (sheetContext, log) => PendantListeningSheet(
                nativeTitle: _l10n.pendantIsListeningTitle,
                onRecordWithPhone: () {
                  Navigator.pop(sheetContext);
                  log.add('phone:${ModalRoute.of(sheetContext)!.isCurrent}');
                },
                onPhoneCall: () {
                  Navigator.pop(sheetContext);
                  log.add('call');
                },
                onKeepPendant: () {
                  Navigator.pop(sheetContext);
                  log.add('keep');
                },
              ));
      expect(row(tester, 'pendant_one_source')!.title, _l10n.oneSourceAtATime);
      await send(tester, 'pendant_record_phone');
      await tester.pumpAndSettle();
      expect(log, ['phone:false']);
      expect(find.byType(PendantListeningSheet), findsNothing);
    });

    testWidgets('the capture details sheet explains and Got It closes it', (tester) async {
      await openSheet(tester,
          (sheetContext, log) => const CaptureDetailsSheet(explanation: 'Audio is safe', nativeTitle: 'Paused'));
      expect(row(tester, 'capture_details_explanation')!.title, 'Audio is safe');
      await send(tester, 'capture_details_ok');
      await tester.pumpAndSettle();
      expect(find.byType(CaptureDetailsSheet), findsNothing);
    });

    testWidgets('without the native host each sheet stays classic', (tester) async {
      await tester.pumpWidget(ChangeNotifierProvider(
          create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {}),
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              home: Scaffold(
                  body:
                      RecordOptionsSheet(nativeTitle: 'Record with', onPickPhoneMic: () {}, onPickPhoneCall: () {})))));
      await tester.pump();
      expect(find.byType(UiKitView), findsNothing);
      expect(find.text(_l10n.recordWithPhoneMicSubtitle), findsOneWidget);
    });
  });
}
