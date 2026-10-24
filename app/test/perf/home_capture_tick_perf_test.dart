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
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/utils/enums.dart';

enum _Live { idle, idleDeviceConnected, pendant, pendantPaused, pendantBatch, phone, phoneAfterPendant }

class _Capture extends ChangeNotifier implements CaptureProvider {
  _Capture(this.live, {this.batch = false});
  @override
  LocalSttFailure? localSttFailure;
  int localRetries = 0;
  @override
  Future<void> retryLocalTranscription() async => localRetries++;
  bool verified = true;
  int? offlineElapsedOverride;
  @override
  bool get pendantCaptureVerified => verified;

  final _Live live;
  final bool failure = false;
  final bool batch;

  /// Phone capture marked `interrupted` by the controller.
  final bool interrupted = false;

  /// The OS holds the microphone (`isCallActive`).
  final bool callActive = false;

  /// The reader paused the phone recording.
  final bool readerPaused = false;
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
  bool offlineMutedState = false;
  int offlineMuteToggles = 0;
  @override
  bool get offlineMuted => offlineMutedState;
  @override
  Future<void> toggleOfflineMute() async {
    offlineMuteToggles++;
    offlineMutedState = !offlineMutedState;
    if (offlineMutedState) {
      offlineElapsedOverride = 125;
    }
    notifyListeners();
  }

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
  int? get offlineRecordingStartedAt => batch ? 1 : null;
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
  Duration callDuration = const Duration(minutes: 3, seconds: 10);
  @override
  List<TranscriptSegment> get transcriptSegments => const [];
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Device extends ChangeNotifier implements DeviceProvider {
  _Device({this.paired = true});
  bool connected = true;
  final bool paired;

  /// Null derives it from [connected]; some tests pin it (a dropped pendant that is not
  /// reconnecting yet).
  final bool? connecting = null;
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

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  for (final hidden in [false, true]) {
    testWidgets('compact capture has no clock rebuilds (hidden=$hidden)', (tester) async {
      final capture = _Capture(_Live.phone);
      final device = _Device(paired: false);
      final call = _Call(PhoneCallState.idle);
      addTearDown(capture.dispose);
      addTearDown(device.dispose);
      addTearDown(call.dispose);
      final semantics = tester.ensureSemantics();
      try {
        await tester.pumpWidget(MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: capture),
            ChangeNotifierProvider<DeviceProvider>.value(value: device),
            ChangeNotifierProvider<PhoneCallProvider>.value(value: call),
          ],
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(body: TickerMode(enabled: !hidden, child: const ConversationCaptureWidget(showsCall: true))),
          ),
        ));
        await tester.pump();
        expect(find.byType(LiveCaptureCard), findsOneWidget);
        var builds = 0;
        final previous = debugOnRebuildDirtyWidget;
        debugOnRebuildDirtyWidget = (element, builtOnce) {
          if (element.widget is LiveCaptureCard) builds++;
          previous?.call(element, builtOnce);
        };
        try {
          for (var i = 0; i < 5; i++) {
            await tester.pump(const Duration(seconds: 1));
          }
        } finally {
          debugOnRebuildDirtyWidget = previous;
        }
        debugPrint('HOME COMPACT CLOCK hidden=$hidden semantics=true: 5 ticks, cardBuilds=$builds');
        expect(builds, 0, reason: 'the compact card shows no elapsed clock; hidden tabs paint no clock either');
        await tester.pumpWidget(const SizedBox.shrink());
      } finally {
        semantics.dispose();
      }
    });
  }
  for (final batch in [false, true]) {
    testWidgets('visible ${batch ? 'batch' : 'call'} clock ticks and catches up after a hidden tab', (tester) async {
      final capture = _Capture(_Live.phone, batch: batch)..offlineElapsedOverride = 125;
      final call = _Call(batch ? PhoneCallState.idle : PhoneCallState.active);
      final device = _Device(paired: false);
      final visible = ValueNotifier(true);
      addTearDown(capture.dispose);
      addTearDown(call.dispose);
      addTearDown(device.dispose);
      addTearDown(visible.dispose);
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: capture),
          ChangeNotifierProvider<DeviceProvider>.value(value: device),
          ChangeNotifierProvider<PhoneCallProvider>.value(value: call),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
              body: ValueListenableBuilder<bool>(
            valueListenable: visible,
            builder: (_, enabled, child) => TickerMode(enabled: enabled, child: child!),
            child: const ConversationCaptureWidget(showsCall: true),
          )),
        ),
      ));
      LiveCaptureCard card() => tester.widget(find.byType(LiveCaptureCard));
      final initial = batch ? 125 : 190;
      expect(card().elapsed?.inSeconds, initial);
      capture.offlineElapsedOverride = initial + 1;
      call.callDuration = Duration(seconds: initial + 1);
      await tester.pump(const Duration(seconds: 1));
      expect(card().elapsed?.inSeconds, initial + 1);
      visible.value = false;
      await tester.pump();
      capture.offlineElapsedOverride = initial + 6;
      call.callDuration = Duration(seconds: initial + 6);
      await tester.pump(const Duration(seconds: 5));
      expect(card().elapsed?.inSeconds, initial + 1, reason: 'hidden clock has no UI timer rebuild');
      visible.value = true;
      await tester.pump();
      expect(card().elapsed?.inSeconds, initial + 6, reason: 'returning to Home displays current elapsed time');
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
