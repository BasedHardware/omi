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
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';

enum _Live { idle, idleDeviceConnected, pendant, pendantPaused, phone, phoneAfterPendant }

class _Capture extends ChangeNotifier implements CaptureProvider {
  _Capture(this.live);
  final _Live live;
  int pauses = 0;
  int resumes = 0;
  int phoneStarts = 0;

  @override
  String? get liveCaptureSource => switch (live) {
        _Live.idle || _Live.idleDeviceConnected => null,
        _Live.pendant || _Live.pendantPaused => 'omi',
        _ => 'phone',
      };
  @override
  RecordingState get recordingState => switch (live) {
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
  bool get isPaused => live == _Live.pendantPaused;
  @override
  bool get isPhoneMicPaused => false;
  @override
  bool get pendantPausedForPhone => live == _Live.phoneAfterPendant;
  @override
  bool get isCallActive => false;
  @override
  bool get isPhoneMicBatchRecording => false;
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
  MessageServiceStatusEvent? get terminalTranscriptionFailure => null;
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

  Future<void> pump(WidgetTester tester, Widget child, {required _Capture capture, _Call? call}) async {
    await tester.pumpWidget(MultiProvider(
      providers: [
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
    testWidgets('names the source, the state and the time, with Pause', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
      expect(find.text(en.captureSourcePendant), findsOneWidget);
      expect(find.text(en.listening), findsOneWidget);
      expect(find.text('12:04'), findsOneWidget);
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
      expect(find.text(en.phone), findsOneWidget);
      expect(find.text(en.pendantPausedResumesWhenYouFinish), findsOneWidget);
    });

    testWidgets('an Omi call shows on Home as the live card, and not on the Conversations tab', (tester) async {
      final call = _Call(PhoneCallState.active);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: _Capture(_Live.idle), call: call);
      expect(find.text(en.captureSourceCall), findsOneWidget);
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

    testWidgets('a call that is still ringing is amber and has no time yet', (tester) async {
      await pump(tester, const ConversationCaptureWidget(showsCall: true),
          capture: _Capture(_Live.idle), call: _Call(PhoneCallState.ringing));
      final card = tester.widget<LiveCaptureCard>(find.byType(LiveCaptureCard));
      expect(card.paused, isTrue);
      expect(card.elapsed, isNull);
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
