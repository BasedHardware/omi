import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/enums.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  BtDevice? get pairedDevice => null;

  @override
  bool get isConnecting => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubPhoneCallProvider extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _DeviceCardCaptureProvider extends CaptureProvider {
  @override
  String? get liveCaptureSource => 'omi';

  @override
  BtDevice? get recordingDevice => BtDevice(id: 'test-device', name: 'Test Omi', type: DeviceType.omi, rssi: -50);

  @override
  bool get havingRecordingDevice => true;

  @override
  bool get recordingDeviceServiceReady => true;
}

class _SocketUpCaptureProvider extends CaptureProvider {
  @override
  bool get transcriptServiceReady => true;
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized or platform channels unavailable
    }
  });

  Future<void> pumpCaptureWidget(WidgetTester tester, CaptureProvider captureProvider) async {
    final deviceProvider = _StubDeviceProvider();
    final connectivityProvider = _StubConnectivityProvider();
    final phoneCallProvider = _StubPhoneCallProvider();
    addTearDown(deviceProvider.dispose);
    addTearDown(connectivityProvider.dispose);
    addTearDown(phoneCallProvider.dispose);

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: MultiProvider(
            providers: [
              ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
              ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivityProvider),
              ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
              ChangeNotifierProvider<PhoneCallProvider>.value(value: phoneCallProvider),
            ],
            child: const ConversationCaptureWidget(),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  group('simplified status indicators (#6672)', () {
    testWidgets('shows terminal live STT failure until the backend is ready again', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.record);

      await pumpCaptureWidget(tester, captureProvider);

      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(
          status: 'stt_failed',
          outcome: 'upstream_error',
          provider: 'deepgram',
          retryable: true,
          reason: 'send_failed',
        ),
      );
      await tester.pump();

      expect(captureProvider.recordingState, RecordingState.record);
      expect(captureProvider.terminalTranscriptionFailure?.status, 'stt_failed');
      final context = tester.element(find.byType(ConversationCaptureWidget));
      // The card carries the short status; the full recording-continues sentence belongs to the
      // capturing page and the card's details sheet.
      expect(find.text(AppLocalizations.of(context).captureNotTranscribing), findsWidgets);
      expect(find.text(AppLocalizations.of(context).transcriptionUnavailableRecordingContinues), findsNothing);

      captureProvider.onMessageEventReceived(MessageServiceStatusEvent(status: 'ready'));
      await tester.pump();

      expect(find.text(AppLocalizations.of(context).captureNotTranscribing), findsNothing);
      expect(find.text(AppLocalizations.of(context).listening), findsWidgets);
    });

    testWidgets('a mic stall (interrupted, OS not holding the mic) reads Reconnecting, not Paused', (tester) async {
      // The controller marks phone capture `interrupted` without the OS holding the mic for a
      // silent-mic stall (the socket still up): capture is restarting the microphone on its own,
      // so it reads Reconnecting and keeps Mute. Only an OS interruption (`isCallActive`) is
      // Paused with no control (#4706), covered in capture_home_ui_test.
      final captureProvider = _SocketUpCaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.interrupted);
      expect(captureProvider.isCallActive, isFalse);

      await pumpCaptureWidget(tester, captureProvider);

      final l10n = AppLocalizations.of(tester.element(find.byType(ConversationCaptureWidget)));
      expect(find.text(l10n.reconnecting), findsOneWidget);
      expect(find.text(l10n.listening), findsNothing);
      // It claims neither "still recording" (the mic is restarting) nor "mic in use".
      expect(find.textContaining(l10n.captureStillRecording), findsNothing);
      expect(find.textContaining(l10n.captureMicInUseElsewhere), findsNothing);
      expect(find.bySemanticsLabel(l10n.mute), findsOneWidget);
    });

    testWidgets('a dropped transcription socket reads Reconnecting, not Paused', (tester) async {
      // The controller flips phone `record` to `interrupted` when the socket closes and reconnects
      // while the microphone keeps recording.
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.interrupted);
      expect(captureProvider.isCallActive, isFalse);
      expect(captureProvider.transcriptServiceReady, isFalse);

      await pumpCaptureWidget(tester, captureProvider);

      final l10n = AppLocalizations.of(tester.element(find.byType(ConversationCaptureWidget)));
      expect(find.text(l10n.reconnecting), findsOneWidget);
      expect(find.textContaining(l10n.captureStillRecording), findsOneWidget);
      expect(find.text(l10n.paused), findsNothing);
      expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget);
    });

    testWidgets('shows Listening during phone mic recording when transcription is down', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.record);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;
      final reconnectText = AppLocalizations.of(context).transcriptionPaused;

      expect(find.text(listeningText), findsWidgets);
      expect(find.text(reconnectText), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('shows Starting, not Listening, while the phone microphone initialises', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.initialising);

      await pumpCaptureWidget(tester, captureProvider);

      final l10n = AppLocalizations.of(tester.element(find.byType(ConversationCaptureWidget)));
      expect(find.text(l10n.captureStarting), findsOneWidget);
      expect(find.text(l10n.listening), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('shows Listening during device recording when transcription is down', (tester) async {
      final captureProvider = _DeviceCardCaptureProvider();
      addTearDown(captureProvider.dispose);
      // The widget fixture supplies an owned device view; ownership transitions are tested through the controller.
      captureProvider.updateRecordingState(RecordingState.deviceRecord);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;
      final reconnectText = AppLocalizations.of(context).transcriptionPaused;

      expect(find.text(listeningText), findsWidgets);
      expect(find.text(reconnectText), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets("the reader's mute overrides Listening during device recording", (tester) async {
      final captureProvider = _DeviceCardCaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.deviceRecord);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;
      // Muted: one word for the reader's pause on every source (the control is Mute/Unmute).
      final mutedText = AppLocalizations.of(context).muted;

      // Initially should show Listening
      expect(find.text(listeningText), findsWidgets);

      // Exercise the production mute path, including its durable preference write.
      await tester.runAsync(() => captureProvider.pauseDeviceRecording());
      await tester.pump();

      // Muted overrides Listening for device recording
      expect(find.text(mutedText), findsWidgets);
    });
  });
}
