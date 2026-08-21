import 'dart:io';

import 'package:fake_async/fake_async.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

/// Minimal EnvFields stub so Env-backed code paths don't hit a
/// LateInitializationError (mirrors capture_provider_test.dart's fixture).
class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:8000/';
  @override
  String? get googleMapsApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

/// Always-connected fake so a successful reconnect looks identical to a real
/// one to TranscriptSegmentSocketService.state.
class _FakeConnectedSocket implements IPureSocket {
  @override
  PureSocketStatus status = PureSocketStatus.connected;

  @override
  Future<bool> connect() async => true;

  @override
  Future disconnect() async {}

  @override
  Future stop() async {}

  @override
  void send(dynamic message) {}

  @override
  void setListener(IPureSocketListener listener) {}

  @override
  void onMessage(dynamic message) {}

  @override
  void onConnected() {}

  @override
  void onClosed() {}

  @override
  void onError(Object err, StackTrace trace) {}
}

/// Counts reconnect attempts instead of hitting the real socket service pool,
/// mirroring capture_provider_test.dart's _GatedSocketCaptureProvider pattern
/// for CaptureProvider.openConversationSocket.
class _CountingSpeechProfileProvider extends SpeechProfileProvider {
  int openCalls = 0;

  @override
  Future<TranscriptSegmentSocketService?> openSpeechProfileSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
  }) async {
    openCalls++;
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      _FakeConnectedSocket(),
      onboardingMode: true,
    );
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return Directory.systemTemp.path;
        return null;
      },
    );
    try {
      Env.init(_TestEnvFields());
    } catch (_) {
      // Env._instance is late final — ignore if already initialized in this isolate.
    }
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  // Regression coverage: previously the onboarding websocket had no reconnect
  // at all. Once it dropped mid-flow, both live mic audio and
  // skipCurrentQuestion() (services/sockets/transcription_service.dart-backed,
  // gated on `_socket?.state == connected`) silently did nothing forever,
  // requiring a full app relaunch to unstick onboarding.
  group('onboarding socket reconnect', () {
    test('reconnects on an interval after the socket drops mid-onboarding, then stops', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider();
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);
        provider.currentQuestionIndex = 3;
        provider.currentQuestion = 'What do you have planned for today?';

        provider.onClosed(1006);
        async.flushMicrotasks();
        expect(provider.openCalls, 0, reason: 'a reconnect is scheduled on an interval, not attempted immediately');

        async.elapse(const Duration(seconds: 5));
        expect(provider.openCalls, 1, reason: 'the first tick must attempt a reconnect');

        // The backend keeps no onboarding state across connections
        // (OnboardingHandler is constructed fresh per websocket), so a
        // reconnect always restarts the question sequence from the top.
        expect(provider.currentQuestionIndex, 0);
        expect(provider.currentQuestion, '');

        // The fake socket reports connected immediately, so the periodic
        // timer must stop rather than opening a second socket on the next
        // tick.
        async.elapse(const Duration(seconds: 15));
        expect(provider.openCalls, 1, reason: 'timer must stop once reconnected, not keep firing');

        provider.dispose();
      });
    });

    test('does not schedule a reconnect once the profile is already completed', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider();
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);
        provider.profileCompleted = true;

        provider.onClosed(1000);
        async.elapse(const Duration(seconds: 30));

        expect(provider.openCalls, 0, reason: 'onboarding already finished; nothing to reconnect');

        provider.dispose();
      });
    });
  });

  // Regression coverage: closeCode 1011 (server-side STT failure) with no
  // user speech captured yet means the STT backend is down, not that the
  // socket hiccuped. Before this fix, every such close scheduled another 5s
  // reconnect forever, spamming the "connection lost" dialog (see
  // speech_profile_widget.dart/page.dart) with no way out except force-
  // quitting, even though "Skip for now" sits right next to it.
  group('speech-profile socket gives up when STT is unavailable', () {
    test('stops reconnecting and surfaces STT_UNAVAILABLE after repeated 1011 closes', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider();
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);

        provider.onClosed(1011);
        expect(provider.error, 'SOCKET_DISCONNECTED');

        provider.onClosed(1011);
        expect(provider.error, 'SOCKET_DISCONNECTED');

        provider.onClosed(1011);
        expect(
          provider.error,
          'STT_UNAVAILABLE',
          reason: 'third consecutive 1011 with no captured speech means STT is down; keep retrying cannot fix that',
        );

        async.elapse(const Duration(seconds: 30));
        expect(provider.openCalls, 0, reason: 'must not keep scheduling reconnects once STT is deemed unavailable');

        provider.dispose();
      });
    });

    test('does not give up on an ordinary disconnect that is not a 1011 STT failure', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider();
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);

        provider.onClosed(1006);
        provider.onClosed(1006);
        provider.onClosed(1006);

        expect(provider.error, 'SOCKET_DISCONNECTED', reason: 'code 1006 is a generic drop, not the STT-down signal');

        async.elapse(const Duration(seconds: 5));
        expect(provider.openCalls, 1, reason: 'an ordinary disconnect must still keep retrying');

        provider.dispose();
      });
    });

    test('does not give up once real speech has been captured', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider();
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);

        provider.onClosed(1011);
        provider.onClosed(1011);

        // Simulate captured speech directly rather than going through
        // onSegmentReceived, which also touches the WavBytesUtil that
        // initialise() (not exercised by this test) normally sets up.
        provider.segments.add(
          TranscriptSegment(
            id: '1',
            text: 'hello',
            speaker: 'SPEAKER_1',
            isUser: true,
            personId: null,
            start: 0,
            end: 1,
            translations: [],
          ),
        );

        provider.onClosed(1011);
        expect(
          provider.error,
          'SOCKET_DISCONNECTED',
          reason: 'speech was captured, so STT is actually working; a later 1011 must not short-circuit to skip',
        );

        provider.dispose();
      });
    });
  });

  // Regression coverage: finalize()'s upload-failure branch commented "still
  // process conversation" but never set profileCompleted, so the "All Done"
  // continue button (gated on provider.profileCompleted in
  // speech_profile_widget.dart) never appeared — trapping the user on the
  // last onboarding question forever whenever the speech-profile upload
  // fails (e.g. BUCKET_SPEECH_PROFILES unconfigured locally).
  group('onboarding completes even when the speech-profile upload fails', () {
    test('marks the profile completed after an upload failure', () {
      final provider = SpeechProfileProvider();

      provider.completeAfterUploadFailure(tooShort: false);

      expect(provider.profileCompleted, isTrue, reason: 'the user must be able to leave onboarding');
      expect(provider.uploadingProfile, isFalse);
      expect(provider.error, 'UPLOAD_FAILED');

      provider.dispose();
    });

    test('marks the profile completed after a too-short-audio failure', () {
      final provider = SpeechProfileProvider();

      provider.completeAfterUploadFailure(tooShort: true);

      expect(provider.profileCompleted, isTrue, reason: 'the user must be able to leave onboarding');
      expect(provider.error, 'TOO_SHORT');

      provider.dispose();
    });
  });
}
