// The Home capture surfaces (David, 2026-09-25): the live card is what's recording now, the round
// button always means "record with this phone", and the header chip shows the battery only.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

enum _Live { idle, idleDeviceConnected, pendant, pendantPaused, pendantBatch, phone, phoneAfterPendant }

class _Capture extends ChangeNotifier implements CaptureProvider {
  _Capture(this.live,
      {this.failure = false,
      this.batch = false,
      this.interrupted = false,
      this.callActive = false,
      this.readerPaused = false});
  bool verified = true;
  int? offlineElapsedOverride;
  @override
  bool get pendantCaptureVerified => verified;

  final _Live live;
  final bool failure;
  final bool batch;

  /// Phone capture marked `interrupted` by the controller.
  final bool interrupted;

  /// The OS holds the microphone (`isCallActive`).
  final bool callActive;

  /// The reader paused the phone recording.
  final bool readerPaused;
  int pauses = 0;
  int resumes = 0;
  int phoneStarts = 0;
  Object? phoneStartFailure;

  @override
  String? get liveCaptureSource => switch (live) {
        _Live.idle || _Live.idleDeviceConnected => null,
        _Live.pendant || _Live.pendantPaused || _Live.pendantBatch => 'omi',
        _ => 'phone',
      };
  @override
  RecordingState get recordingState => interrupted
      ? RecordingState.interrupted
      : readerPaused
          ? RecordingState.pause
          : switch (live) {
              _Live.idle || _Live.idleDeviceConnected => RecordingState.stop,
              _Live.pendant || _Live.pendantBatch => RecordingState.deviceRecord,
              _Live.pendantPaused => RecordingState.pause,
              _ => RecordingState.record,
            };
  @override
  bool get havingRecordingDevice => live != _Live.idle && live != _Live.phone;
  @override
  BtDevice? get recordingDevice => null;
  @override
  bool get isPaused => live == _Live.pendantPaused || readerPaused;
  @override
  bool get isPhoneMicPaused => readerPaused;
  @override
  bool get pendantPausedForPhone => live == _Live.phoneAfterPendant;
  @override
  bool get isCallActive => callActive;
  @override
  bool get isPhoneMicBatchRecording => batch;
  @override
  bool get offlineMuted => false;
  @override
  int? get offlineRecordingElapsedSeconds => offlineElapsedOverride ?? (batch ? 125 : null);
  @override
  bool get isPendantBatchRecording => live == _Live.pendantBatch;
  @override
  DateTime? get liveCaptureStartedAt => live == _Live.idle || live == _Live.idleDeviceConnected
      ? null
      : DateTime.now().subtract(const Duration(minutes: 12, seconds: 4));
  @override
  List<TranscriptSegment> get segments => live == _Live.idle
      ? []
      : [
          TranscriptSegment(
              id: '1',
              text: 'Keep the pendant flow as it is.',
              speaker: 'SPEAKER_0',
              isUser: true,
              personId: null,
              start: 0,
              end: 3,
              translations: []),
        ];
  @override
  List<ConversationPhoto> get photos => const [];
  @override
  int? get offlineRecordingStartedAt => null;
  @override
  Duration? get customSttBufferingDuration => null;
  @override
  MessageServiceStatusEvent? get terminalTranscriptionFailure =>
      failure ? MessageServiceStatusEvent(status: 'stt_failed') : null;
  @override
  bool get recordingDeviceServiceReady => true;
  @override
  bool get transcriptServiceReady => true;
  @override
  List<MessageEvent> get transcriptionServiceStatuses => const [];
  @override
  bool get isConversationMarkedForStarring => false;
  @override
  Future<void> pauseCapture() async => pauses++;
  @override
  Future<void> resumeCapture() async => resumes++;
  @override
  Future<void> streamRecording({bool resumeCapture = true}) async {
    phoneStarts++;
    final failure = phoneStartFailure;
    if (failure != null) throw failure;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Call extends ChangeNotifier implements PhoneCallProvider {
  _Call(this.callState);
  @override
  final PhoneCallState callState;
  @override
  Duration get callDuration => const Duration(minutes: 3, seconds: 10);
  @override
  List<TranscriptSegment> get transcriptSegments => const [];
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Device extends ChangeNotifier implements DeviceProvider {
  _Device({this.connected = true, this.paired = true, this.connecting});
  bool connected;
  final bool paired;

  /// Null derives it from [connected]; some tests pin it (a dropped pendant that is not
  /// reconnecting yet).
  final bool? connecting;
  static final _pendant = BtDevice(id: 'p', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? get connectedDevice => connected ? _pendant : null;
  @override
  BtDevice? get pairedDevice => paired ? _pendant : null;
  @override
  bool get isConnecting => connecting ?? !connected;
  void drop() {
    connected = false;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pump(WidgetTester tester, Widget child,
      {required _Capture capture, _Call? call, _Device? device}) async {
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: device ?? _Device(paired: false)),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<PhoneCallProvider>.value(value: call ?? _Call(PhoneCallState.idle)),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: _Connectivity()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildOmiTheme(),
        home: Scaffold(body: Center(child: child)),
      ),
    ));
    await tester.pump();
  }

  group('live card', () {
    testWidgets('names the source as a glyph, the state and the latest line, with Pause', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      // The source is a glyph with a spoken name, not a text label (David, 2026-09-26).
      expect(find.text(en.captureSourcePendant), findsNothing);
      // The card is one button, so the spoken name merges into its label.
      expect(find.bySemanticsLabel(RegExp('^${en.captureSourcePendant}\n')), findsOneWidget);
      expect(find.text(en.listening), findsOneWidget);
      // The session clock is not the conversation, so the pill does not show it.
      expect(find.text('12:04'), findsNothing);
      expect(find.text('Keep the pendant flow as it is.'), findsOneWidget);
      final statusBox = tester.getRect(find.text(en.listening));
      final previewBox = tester.getRect(find.text('Keep the pendant flow as it is.'));
      expect((statusBox.center.dy - previewBox.center.dy).abs(), lessThan(4));
      expect(find.bySemanticsLabel(en.pause), findsOneWidget);
      expect(find.byIcon(Icons.mic), findsNothing, reason: 'mics belong to Ask Omi');

      await tester.tap(find.byType(OmiIconButton));
      await tester.pump();
      expect(capture.pauses, 1);
    });

    testWidgets('a paused pendant offers Resume', (tester) async {
      final capture = _Capture(_Live.pendantPaused);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      expect(find.text(en.paused), findsOneWidget);
      await tester.tap(find.bySemanticsLabel(en.resume));
      await tester.pump();
      expect(capture.resumes, 1);
    });

    testWidgets('the phone taking over from the pendant says the pendant waits', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.phoneAfterPendant));
      expect(find.bySemanticsLabel(RegExp('^${en.phone}\n')), findsOneWidget);
      expect(find.text(en.pendantPausedResumesWhenYouFinish), findsOneWidget);
    });

    testWidgets('an Omi call shows on Home as the live card, and not on the Conversations tab', (tester) async {
      final call = _Call(PhoneCallState.active);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.idle), call: call);
      expect(find.bySemanticsLabel(RegExp('^${en.captureSourceCall}\n')), findsOneWidget);
      expect(find.text('3:10'), findsOneWidget);
      expect(find.byType(OmiIconButton), findsNothing, reason: 'the call page owns the call controls');

      await pump(tester, const ConversationCaptureWidget(), capture: _Capture(_Live.idle), call: call);
      expect(find.byType(LiveCaptureCard), findsNothing);
    });

    testWidgets('hidden when nothing is live, including a connected pendant that is not capturing', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.idle));
      expect(find.byType(LiveCaptureCard), findsNothing);
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.idleDeviceConnected));
      expect(find.byType(LiveCaptureCard), findsNothing);
      expect(find.byIcon(Icons.record_voice_over), findsNothing, reason: 'the old header is gone');
    });

    testWidgets('a call that is still ringing says so and has no time yet', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.idle), call: _Call(PhoneCallState.ringing));
      final card = tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard));
      expect(card.status, en.callStateRinging);
      expect(card.elapsed, isNull);
      expect(card.explanation, isNull, reason: 'ringing is not a problem');
    });

    testWidgets('a transcription outage is still live: Pause, a warning, and a sheet that explains', (tester) async {
      final capture = _Capture(_Live.pendant, failure: true);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      expect(find.text(en.captureNotTranscribing), findsOneWidget);
      expect(find.text(en.captureAudioSavedTranscribesLater), findsOneWidget);
      expect(find.textContaining('12:04'), findsNothing);
      expect(find.byIcon(Icons.warning_amber_rounded), findsNothing);
      // The control matches the state: capture is live, so it pauses (it never reads Resume here).
      expect(find.bySemanticsLabel(en.resume), findsNothing);
      await tester.tap(find.bySemanticsLabel(en.pause));
      await tester.pump();
      expect(capture.pauses, 1);
      expect(capture.resumes, 0);

      await tester.tap(find.text(en.captureNotTranscribing));
      await tester.pumpAndSettle();
      expect(find.text(en.transcriptionUnavailableRecordingContinues), findsOneWidget);
      await tester.tap(find.text(en.gotIt));
      await tester.pumpAndSettle();
      expect(find.text(en.transcriptionUnavailableRecordingContinues), findsNothing);
    });

    testWidgets('a healthy card has no warning and no details sheet', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.pendant));
      expect(find.byIcon(Icons.warning_amber_rounded), findsNothing);
      final card = tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard));
      expect(card.explanation, isNull);
    });

    testWidgets('the card is one button that opens the live transcript', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.pendant));
      expect(find.bySemanticsLabel(RegExp(en.captureSourcePendant)), findsWidgets);
      final semantics = tester.getSemantics(find.byType(LiveCaptureCard));
      expect(semantics, isNotNull);
    });

    testWidgets('photo-capture devices have no Pause', (tester) async {
      expect(
          LiveCaptureCard.canPause(BtDevice(id: 'g', name: 'Glass', type: DeviceType.openglass, rssi: -40),
              source: 'openglass'),
          isFalse);
      expect(LiveCaptureCard.canPause(null, source: 'phone'), isTrue);
    });
  });

  group('phone interruptions', () {
    testWidgets('the OS holding the mic: Paused, the cause, a sheet, and no control', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.phone, interrupted: true, callActive: true));
      expect(find.text(en.paused), findsOneWidget);
      expect(find.textContaining(en.captureMicInUseElsewhere), findsOneWidget);
      expect(find.byType(OmiIconButton), findsNothing, reason: 'the OS resumes capture itself');
    });

    testWidgets('an interruption on a recording the reader paused keeps Resume', (tester) async {
      final capture = _Capture(_Live.phone, interrupted: true, callActive: true, readerPaused: true);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      expect(find.text(en.paused), findsOneWidget);
      expect(find.textContaining(en.captureMicInUseElsewhere), findsNothing);
      await tester.tap(find.bySemanticsLabel(en.resume));
      await tester.pump();
      expect(capture.resumes, 1);
    });
  });

  group('pill fits small screens and large text', () {
    Future<void> pumpPill(WidgetTester tester,
        {required double width, required double textScale, required String status}) async {
      tester.view.physicalSize = Size(width, 200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildOmiTheme(),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: Scaffold(
          body: Align(
            alignment: Alignment.topLeft,
            child: LiveCaptureCard(
              source: 'omi',
              status: status,
              lastLine: 'Keep the pendant flow as it is.',
              compact: true,
              onPauseToggle: () {},
            ),
          ),
        ),
      ));
      await tester.pump();
    }

    testWidgets('a long localized status yields before the pause, never overflows', (tester) async {
      // A fold-cover-class width: after the pill's own padding the row is 266pt, so the old
      // 168pt status cap alone overflowed it. The cap must shrink to what is left.
      const status = 'Verbindung wird wiederhergestellt';
      await pumpPill(tester, width: 280, textScale: 1.0, status: status);
      expect(tester.takeException(), isNull, reason: 'the pill row must not overflow');
      expect(tester.getSize(find.text(status)).width, lessThanOrEqualTo(166),
          reason: 'the status cap yields on a narrow row');
      final pause = tester.getRect(find.byIcon(Icons.pause_rounded));
      expect(pause.right, lessThanOrEqualTo(278), reason: 'the pause control stays inside the row');

      await pumpPill(tester, width: 280, textScale: 2.0, status: status);
      expect(tester.takeException(), isNull, reason: 'large text must not overflow the pill either');
      expect(tester.getSize(find.text(status)).width, lessThanOrEqualTo(166));
    });

    testWidgets('an English status that fits keeps its whole width', (tester) async {
      await pumpPill(tester, width: 296, textScale: 1.0, status: en.listening);
      expect(tester.takeException(), isNull);
      // Not split to an even share of the row (which would starve a status that fits):
      // "Listening" is ~137pt whole at 1.0x.
      expect(tester.getSize(find.text(en.listening)).width, greaterThan(130));
      await pumpPill(tester, width: 296, textScale: 2.0, status: en.listening);
      expect(tester.takeException(), isNull);
    });
  });

  group('pendant disconnect', () {
    testWidgets('a pendant that drops mid-capture shows Disconnected, not nothing', (tester) async {
      final device = _Device();
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.pendant), device: device);
      expect(find.text(en.listening), findsOneWidget);

      // The controller forgets the device: no live source, the pendant is paired but not connected.
      device.drop();
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.idleDeviceConnected), device: device);
      expect(find.text(en.disconnected), findsOneWidget);
      expect(find.textContaining(en.reconnecting), findsOneWidget);
      // The session clock is gone, so a drop has nothing to freeze or advance.
      expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
      expect(find.textContaining('12:04'), findsNothing);
      await tester.pump(const Duration(seconds: 3));
      expect(find.textContaining('12:04'), findsNothing);
      await tester.tap(find.text(en.disconnected));
      await tester.pumpAndSettle();
      expect(find.text(en.capturePendantDisconnectedDetail), findsOneWidget);
    });

    testWidgets('a dropped pendant that is not reconnecting yet still says what happens next', (tester) async {
      final device = _Device(connecting: false);
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.pendant), device: device);
      expect(find.text(en.listening), findsOneWidget);

      device.drop();
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.idleDeviceConnected), device: device);
      expect(find.text(en.disconnected), findsOneWidget);
      // Not a bare "Disconnected": the row keeps its inline reassurance, the sheet keeps the why.
      expect(find.text(en.capturePendantDisconnectedShort), findsOneWidget);
      expect(find.textContaining(en.reconnecting), findsNothing);
      await tester.tap(find.text(en.disconnected));
      await tester.pumpAndSettle();
      expect(find.text(en.capturePendantDisconnectedDetail), findsOneWidget);
      await tester.tap(find.text(en.gotIt));
      await tester.pumpAndSettle();
    });

    testWidgets('a paired pendant that was never capturing stays hidden', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.idle), device: _Device(connected: false));
      expect(find.byType(LiveCaptureCard), findsNothing);
    });
  });

  group('Transcribe Later card', () {
    testWidgets('storage full: no Pause, a warning that explains, controls at least 44pt', (tester) async {
      SharedPreferences.setMockInitialValues({'batchStorageFull': true});
      await SharedPreferencesUtil.init();
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.phone, batch: true));
      expect(find.text(en.paused), findsOneWidget);
      expect(find.textContaining(en.capturePhoneStorageFull), findsOneWidget);
      expect(find.bySemanticsLabel(en.pause), findsNothing);
      for (final label in [en.newRecording, en.stop]) {
        final size = tester.getSize(find.ancestor(of: find.text(label), matching: find.byType(TextButton)));
        expect(size.height, greaterThanOrEqualTo(44));
      }
      await tester.tap(find.text(en.paused));
      await tester.pumpAndSettle();
      expect(find.text(en.transcribeLaterStorageFull), findsOneWidget);
    });

    testWidgets('unverified pendant batch keeps controls without claiming saved audio or elapsed time', (tester) async {
      SharedPreferencesUtil().batchModeEnabled = true;
      addTearDown(() => SharedPreferencesUtil().batchModeEnabled = false);
      final capture = _Capture(_Live.pendantBatch)
        ..verified = false
        ..offlineElapsedOverride = 125;
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      expect(find.text(en.captureSourcePendant), findsOneWidget);
      expect(find.text(en.pause), findsOneWidget);
      expect(find.text(en.captureAudioSavedTranscribesLater), findsNothing);
      expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
      await tester.pump(const Duration(minutes: 1));
      expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('recording: the live card layout with a 0:14-style timer', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.phone, batch: true));
      expect(find.text(en.recording), findsOneWidget);
      expect(find.text('2:05  ·  ${en.captureAudioSavedTranscribesLater}'), findsOneWidget);
      expect(find.text(en.pause), findsOneWidget);
      expect(find.text(en.transcribeLaterNote), findsNothing, reason: 'settings copy is not a status');
    });
  });

  testWidgets('unverified pendant keeps its transcript and controls without Listening or a timer', (tester) async {
    final capture = _Capture(_Live.pendant)..verified = false;
    await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
    expect(find.byType(LiveCaptureCard), findsOneWidget);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).onPauseToggle, isNotNull);
    expect(find.text(en.captureSourcePendant), findsOneWidget);
    expect(find.text(en.listening), findsNothing);
    expect(find.textContaining('Keep the pendant flow as it is.'), findsOneWidget);
    await tester.pump(const Duration(minutes: 1));
    expect(find.byType(LiveCaptureCard), findsOneWidget);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).onPauseToggle, isNotNull);
    expect(find.text(en.captureSourcePendant), findsOneWidget);
    expect(find.text(en.listening), findsNothing);
    expect(find.textContaining('Keep the pendant flow as it is.'), findsOneWidget);
    capture.verified = true;
    capture.notifyListeners();
    await tester.pump();
    expect(find.byType(LiveCaptureCard), findsOneWidget);
    expect(find.text(en.listening), findsOneWidget);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
    capture.verified = false;
    capture.notifyListeners();
    await tester.pump();
    expect(find.byType(LiveCaptureCard), findsOneWidget);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, isNull);
    expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).onPauseToggle, isNotNull);
    expect(find.text(en.captureSourcePendant), findsOneWidget);
    expect(find.text(en.listening), findsNothing);
    expect(find.textContaining('Keep the pendant flow as it is.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  group('record-with-this-phone button', () {
    testWidgets('idle: a white dot and a badge that opens the ways to record', (tester) async {
      await pump(tester, const HomeRecordButton(), capture: _Capture(_Live.idle));
      expect(find.bySemanticsLabel(en.startRecording), findsOneWidget);
      await tester.tap(find.bySemanticsLabel(en.moreWaysToRecord));
      await tester.pumpAndSettle();
      expect(find.text(en.recordWith), findsOneWidget);
      expect(find.text(en.captureSourcePhoneMic), findsOneWidget);
      expect(find.text(en.phoneCall), findsOneWidget);
    });

    testWidgets('while the pendant records, a tap explains instead of taking over', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(tester, const HomeRecordButton(), capture: capture);
      await tester.tap(find.bySemanticsLabel(en.startRecording));
      await tester.pumpAndSettle();
      expect(find.text(en.pendantIsListeningTitle), findsOneWidget);
      expect(capture.phoneStarts, 0, reason: 'never a silent takeover');

      await tester.tap(find.text(en.keepUsingPendant));
      await tester.pumpAndSettle();
      expect(find.text(en.pendantIsListeningTitle), findsNothing);
      expect(capture.phoneStarts, 0);
    });

    testWidgets('a Transcribe Later pendant rejects phone takeover with visible feedback', (tester) async {
      final capture = _Capture(_Live.pendantBatch);
      await pump(tester, const HomeRecordButton(), capture: capture);
      await tester.tap(find.bySemanticsLabel(en.startRecording));
      await tester.pump();
      expect(find.text(en.phoneRecordingBlockedByPendantBatch), findsOneWidget);
      expect(capture.phoneStarts, 0);
      expect(find.text(en.recordWith), findsNothing);
    });

    testWidgets('a start that fails says so and never opens the capturing page', (tester) async {
      final capture = _Capture(_Live.idle)..phoneStartFailure = StateError('refused');
      await pump(tester, const HomeRecordButton(), capture: capture);
      await tester.tap(find.bySemanticsLabel(en.startRecording));
      await tester.pump();
      expect(capture.phoneStarts, 1);
      expect(find.text(en.somethingWentWrong), findsOneWidget);
      expect(find.byType(ConversationCapturingPage), findsNothing);
    });

    testWidgets('a start that resolves without phone ownership navigates nowhere', (tester) async {
      final capture = _Capture(_Live.idle);
      await pump(tester, const HomeRecordButton(), capture: capture);
      await tester.tap(find.bySemanticsLabel(en.startRecording));
      await tester.pump();
      expect(capture.phoneStarts, 1);
      expect(find.byType(ConversationCapturingPage), findsNothing);
      expect(find.text(en.somethingWentWrong), findsNothing, reason: 'a refusal is not an error toast');
    });

    testWidgets('during an Omi call the button never starts a recording', (tester) async {
      final capture = _Capture(_Live.idle);
      await pump(tester, const HomeRecordButton(), capture: capture, call: _Call(PhoneCallState.active));
      await tester.tap(find.bySemanticsLabel(en.startRecording));
      expect(capture.phoneStarts, 0, reason: 'the tap opens the call page instead');
      await tester.pumpWidget(const SizedBox()); // the call page itself is not under test here
    });

    testWidgets('the badge is fully tappable and does not cover the circle\'s centre', (tester) async {
      await pump(tester, const HomeRecordButton(), capture: _Capture(_Live.idle));
      final badge = tester.getRect(find
          .ancestor(of: find.byIcon(Icons.keyboard_arrow_down_rounded), matching: find.byType(GestureDetector))
          .first);
      final button = tester.getRect(find.byType(HomeRecordButton));
      expect(badge.width, greaterThanOrEqualTo(30));
      expect(button.inflate(0.1).contains(badge.topLeft) && button.inflate(0.1).contains(badge.bottomRight), isTrue,
          reason: 'a Stack only hit-tests inside its own box');
      expect(badge.contains(button.center), isFalse);
    });

    testWidgets('while the phone records, the button is its stop', (tester) async {
      await pump(tester, const HomeRecordButton(), capture: _Capture(_Live.phone));
      expect(find.bySemanticsLabel(en.stopRecording), findsOneWidget);
      expect(find.bySemanticsLabel(en.moreWaysToRecord), findsNothing);
    });
  });

  group('battery glyph', () {
    testWidgets('red only when critically low', (tester) async {
      await tester.pumpWidget(const Directionality(
        textDirection: TextDirection.ltr,
        child: Row(children: [BatteryGlyph(level: 72, critical: false), BatteryGlyph(level: 12, critical: true)]),
      ));
      final glyphs = tester.widgetList<BatteryGlyph>(find.byType(BatteryGlyph)).toList();
      expect(glyphs.map((g) => g.critical), [false, true]);
      expect(tester.getSize(find.byType(BatteryGlyph).first), const Size(20, 10));
    });
  });
}
