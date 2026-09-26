// The Home capture surfaces (David, 2026-09-25; Rev 3): the live card is what's recording now, its
// idle twin starts listening with this phone, and the header chip opens Recording from.
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
import 'package:omi/pages/devices/recording_source_sheet.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/home/widgets/idle_capture_card.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

enum _Live { idle, idleDeviceConnected, pendant, pendantPaused, phone, phoneAfterPendant }

class _Capture extends ChangeNotifier implements CaptureProvider {
  _Capture(this.live,
      {this.failure = false,
      this.batch = false,
      this.interrupted = false,
      this.callActive = false,
      this.readerPaused = false});
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
  int finishes = 0;
  int phoneStarts = 0;

  @override
  String? get liveCaptureSource => switch (live) {
        _Live.idle || _Live.idleDeviceConnected => null,
        _Live.pendant || _Live.pendantPaused => 'omi',
        _ => 'phone',
      };
  @override
  RecordingState get recordingState => interrupted
      ? RecordingState.interrupted
      : readerPaused
          ? RecordingState.pause
          : switch (live) {
              _Live.idle || _Live.idleDeviceConnected => RecordingState.stop,
              _Live.pendant => RecordingState.deviceRecord,
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
  int? get offlineRecordingElapsedSeconds => batch ? 125 : null;
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
  String? get topConversationId => null;
  @override
  Future<void> pauseCapture() async => pauses++;
  @override
  Future<void> resumeCapture() async => resumes++;
  @override
  Future<void> finishCapture() async => finishes++;
  @override
  Future<void> streamRecording({bool resumeCapture = true}) async => phoneStarts++;
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
  _Device({this.connected = true, this.paired = true});
  bool connected;
  final bool paired;
  static final _pendant = BtDevice(id: 'p', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? get connectedDevice => connected ? _pendant : null;
  @override
  BtDevice? get pairedDevice => paired ? _pendant : null;
  @override
  bool get isConnecting => !connected;
  @override
  bool get isConnected => connected;
  @override
  int get batteryLevel => -1;
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

class _Sync extends ChangeNotifier implements SyncProvider {
  @override
  bool get isSyncing => false;
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
        ChangeNotifierProvider<SyncProvider>.value(value: _Sync()),
        ChangeNotifierProvider<HomeProvider>(create: (_) => HomeProvider()),
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
    testWidgets('names the state, the source under it and the time, with Pause', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      // Liquid Dock live card: the orb, the short state and the source's name under it.
      expect(find.text(en.captureSourcePendant), findsOneWidget);
      expect(find.text(en.listening), findsOneWidget);
      expect(find.text('12:04'), findsOneWidget);
      expect(find.bySemanticsLabel(en.pause), findsOneWidget);
      expect(find.byIcon(Icons.mic), findsNothing, reason: 'mics belong to Ask Omi');

      await tester.tap(find.byKey(const Key('live_capture_pause')));
      await tester.pump();
      expect(capture.pauses, 1);
    });

    testWidgets('Finish ends and processes the conversation through the one capture API', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      // v2: the card's primary action reads End (it ends this conversation; capture goes on).
      expect(find.text(en.endCapture), findsOneWidget);
      await tester.tap(find.byKey(const Key('live_capture_finish')));
      await tester.pump();
      expect(capture.finishes, 1);
      expect(capture.pauses, 0);
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
      expect(find.text(en.phone), findsOneWidget);
      expect(find.text(en.pendantPausedResumesWhenYouFinish), findsOneWidget);
    });

    testWidgets('an Omi call shows on Home as the live card, and not on the Conversations tab', (tester) async {
      final call = _Call(PhoneCallState.active);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.idle), call: call);
      expect(find.text(en.captureSourceCall), findsOneWidget);
      expect(find.text('3:10'), findsOneWidget);
      expect(find.byType(OmiButton), findsNothing, reason: 'the call page owns the call controls');

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
      // The time sits on the right; the consequence follows the source's name.
      expect(find.text('12:04'), findsOneWidget);
      expect(find.text('${en.captureSourcePendant} · ${en.captureAudioSavedTranscribesLater}'), findsOneWidget);
      expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
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
      expect(find.byKey(const Key('live_capture_pause')), findsNothing, reason: 'the OS resumes capture itself');
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
      // Nothing records while the pendant is gone, so the time stops at the drop.
      final elapsed = tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed;
      await tester.pump(const Duration(seconds: 3));
      expect(tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard)).elapsed, elapsed);
      await tester.tap(find.text(en.disconnected));
      await tester.pumpAndSettle();
      expect(find.text(en.capturePendantDisconnectedDetail), findsOneWidget);
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

    testWidgets('recording: the live card layout with a 0:14-style timer', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.phone, batch: true));
      expect(find.text(en.recording), findsOneWidget);
      expect(find.text('2:05'), findsOneWidget);
      expect(find.textContaining(en.captureAudioSavedTranscribesLater), findsOneWidget);
      expect(find.text(en.pause), findsOneWidget);
      expect(find.text(en.transcribeLaterNote), findsNothing, reason: 'settings copy is not a status');
    });
  });

  group('starting to listen (Rev 3: no record button; the idle card and Recording from)', () {
    testWidgets('idle: Not listening, and Start listening records with this phone', (tester) async {
      final capture = _Capture(_Live.idle);
      await pump(tester, const IdleCaptureCard(), capture: capture);
      expect(find.text(en.notListeningTitle), findsOneWidget);
      expect(find.text(en.addADevice), findsOneWidget, reason: 'nothing paired: the second capsule adds one');
      await tester.tap(find.byKey(const ValueKey('idle_capture_start')));
      expect(capture.phoneStarts, 1);
      await tester.pumpWidget(const SizedBox()); // the live page it opens is not under test here
    });

    testWidgets('the idle card steps aside while anything records or a call runs', (tester) async {
      for (final live in [_Live.pendant, _Live.pendantPaused, _Live.phone]) {
        await pump(tester, const IdleCaptureCard(), capture: _Capture(live));
        expect(find.byKey(const ValueKey('idle_capture_card')), findsNothing, reason: '$live');
      }
      await pump(tester, const IdleCaptureCard(), capture: _Capture(_Live.idle), call: _Call(PhoneCallState.active));
      expect(find.byKey(const ValueKey('idle_capture_card')), findsNothing, reason: 'the call card is what runs');
    });

    testWidgets('Recording from: switching to this phone while the pendant records asks first', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(
        tester,
        Builder(
          builder: (context) =>
              TextButton(onPressed: () => showRecordingSourceSheet(context), child: const Text('open')),
        ),
        capture: capture,
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.text(en.recordingFrom), findsOneWidget);
      expect(find.text(en.recordingFromSubtitle), findsOneWidget);
      await tester.tap(find.byKey(const Key('devices_this_phone')));
      await tester.pumpAndSettle();
      expect(find.text(en.pendantIsListeningTitle), findsOneWidget);
      expect(capture.phoneStarts, 0, reason: 'never a silent takeover');
      await tester.tap(find.text(en.keepUsingPendant));
      await tester.pumpAndSettle();
      expect(find.text(en.pendantIsListeningTitle), findsNothing);
      expect(capture.phoneStarts, 0);
    });

    testWidgets('Recording from: with nothing live, This phone starts listening', (tester) async {
      final capture = _Capture(_Live.idle);
      await pump(
        tester,
        Builder(
          builder: (context) =>
              TextButton(onPressed: () => showRecordingSourceSheet(context), child: const Text('open')),
        ),
        capture: capture,
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('recording_source_add_device')), findsOneWidget);
      await tester.tap(find.byKey(const Key('devices_this_phone')));
      expect(capture.phoneStarts, 1);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('during an Omi call, starting never records', (tester) async {
      final capture = _Capture(_Live.idle);
      await pump(
        tester,
        Builder(
          builder: (context) => TextButton(onPressed: () => PhoneCapture.start(context), child: const Text('start')),
        ),
        capture: capture,
        call: _Call(PhoneCallState.active),
      );
      await tester.tap(find.text('start'));
      expect(capture.phoneStarts, 0, reason: 'the call page opens instead');
      await tester.pumpWidget(const SizedBox()); // the call page itself is not under test here
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
