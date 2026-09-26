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
  _Capture(this.live);
  final _Live live;
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

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Devices extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get pairedDevice => null;
  @override
  bool get isConnected => false;
  @override
  bool get isConnecting => false;
  @override
  int get batteryLevel => -1;
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

  Future<void> pump(WidgetTester tester, Widget child, {required _Capture capture, _Call? call}) async {
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<PhoneCallProvider>.value(value: call ?? _Call(PhoneCallState.idle)),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: _Connectivity()),
        ChangeNotifierProvider<DeviceProvider>.value(value: _Devices()),
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
    testWidgets('names the source, the state and the time, with Pause', (tester) async {
      final capture = _Capture(_Live.pendant);
      await pump(tester, const ConversationCaptureWidget(showsCall: true), capture: capture);
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
