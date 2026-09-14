import 'dart:async';
import 'dart:io';

import 'package:fake_async/fake_async.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/audio/wav_bytes.dart';

/// Minimal EnvFields stub so Env-backed code paths don't hit a
/// LateInitializationError (mirrors capture_provider_test.dart's fixture).
class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:8000/';
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
  CustomSttConfig? lastCustomSttConfig;

  /// What resolveLocalSttConfig() returns: null means "no on-device model on
  /// this platform" (the default, matching the pre-fallback behavior).
  CustomSttConfig? localSttConfig;
  Completer<CustomSttConfig?>? pendingLocalConfig;
  int resolveCalls = 0;

  @override
  Future<CustomSttConfig?> resolveLocalSttConfig() async {
    resolveCalls++;
    return pendingLocalConfig == null ? localSttConfig : await pendingLocalConfig!.future;
  }

  @override
  Future<TranscriptSegmentSocketService?> openSpeechProfileSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    bool speechProfileRedo = false,
    CustomSttConfig? customSttConfig,
  }) async {
    openCalls++;
    lastCustomSttConfig = customSttConfig;
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      _FakeConnectedSocket(),
      onboardingMode: true,
    );
  }
}

/// Counts finalize() calls instead of uploading anything.
class _FinalizeCountingProvider extends SpeechProfileProvider {
  int finalizeCalls = 0;

  @override
  Future finalize() async {
    finalizeCalls++;
  }
}

class _OnboardingFinalizeProvider extends _FinalizeCountingProvider {
  @override
  bool get isOnboardingFlow => true;
}

class _BrokenWavStorage extends Fake implements WavBytesUtil {
  @override
  Future<Never> createWavFile({String? filename, int removeLastNSeconds = 0}) async =>
      throw const FileSystemException('disk full');
}

/// Fails [failTimes] upload attempts, then succeeds. [tooShort] throws the
/// backend duration-cap error so retry logic can refuse to retry it.
class _FlakyUploadProvider extends SpeechProfileProvider {
  _FlakyUploadProvider({required this.failTimes, this.tooShort = false});

  final int failTimes;
  final bool tooShort;
  int uploadAttempts = 0;

  @override
  Future<bool> uploadSpeechProfile(File file) async {
    uploadAttempts++;
    if (tooShort) {
      throw Exception('Failed to upload sample (400): Audio duration is invalid (must be 5-180 seconds)');
    }
    if (uploadAttempts <= failTimes) {
      throw Exception('Failed to upload sample (500): boom');
    }
    return true;
  }
}

TranscriptSegment _userSegment(String id, String text, {int speakerId = 0}) => TranscriptSegment(
      id: id,
      text: text,
      speaker: 'SPEAKER_$speakerId',
      isUser: true,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    );

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
        // The third strike first checks (asynchronously) whether on-device STT
        // can take over; with no local model that resolves to STT_UNAVAILABLE.
        async.flushMicrotasks();
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

  // When the backend's streaming STT is down but this platform can transcribe
  // on-device, the question flow must continue locally instead of dead-ending
  // in STT_UNAVAILABLE: the backend accepts client-supplied transcripts in
  // custom-STT mode, and the voice print is built from the uploaded audio, not
  // the transcript, so nothing about the resulting profile changes.
  group('falls back to on-device STT when the backend STT is unavailable', () {
    const localConfig = CustomSttConfig(provider: SttProvider.onDeviceWhisper, language: 'en');

    test('switches to on-device STT after repeated 1011 closes and reconnects with it', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider()..localSttConfig = localConfig;
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);

        provider.onClosed(1011);
        provider.onClosed(1011);
        provider.onClosed(1011);
        async.flushMicrotasks();

        expect(provider.usingLocalStt, isTrue);
        expect(provider.info, 'LOCAL_STT_FALLBACK');
        expect(provider.error, isNot('STT_UNAVAILABLE'), reason: 'a usable local model means the flow can go on');

        async.elapse(const Duration(seconds: 5));
        expect(provider.openCalls, 1, reason: 'the fallback must reconnect rather than leave the socket dead');
        expect(provider.lastCustomSttConfig, same(localConfig),
            reason: 'the reconnect must carry the local STT config');

        provider.dispose();
      });
    });

    test('still surfaces STT_UNAVAILABLE when on-device STT is also unavailable', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider(); // localSttConfig stays null
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);

        provider.onClosed(1011);
        provider.onClosed(1011);
        provider.onClosed(1011);
        async.flushMicrotasks();

        expect(provider.usingLocalStt, isFalse);
        expect(provider.error, 'STT_UNAVAILABLE');

        async.elapse(const Duration(seconds: 30));
        expect(provider.openCalls, 0);

        provider.dispose();
      });
    });

    test('a 1011 storm while already on on-device STT gives up instead of looping', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider()..localSttConfig = localConfig;
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);

        for (var i = 0; i < 3; i++) {
          provider.onClosed(1011);
        }
        async.flushMicrotasks();
        expect(provider.usingLocalStt, isTrue);

        for (var i = 0; i < 3; i++) {
          provider.onClosed(1011);
        }
        async.flushMicrotasks();
        expect(provider.error, 'STT_UNAVAILABLE', reason: 'the fallback is a one-way switch, not a retry loop');

        provider.dispose();
      });
    });

    test('enableLocalStt() before initialise() makes the first socket use the local config', () {
      fakeAsync((async) {
        final provider = _CountingSpeechProfileProvider()..localSttConfig = localConfig;
        var enabled = false;
        provider.enableLocalStt().then((value) => enabled = value);
        async.flushMicrotasks();
        expect(enabled, isTrue);
        expect(provider.usingLocalStt, isTrue);

        // Drive the same reconnect path initialise()/_initiateWebsocket use.
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);
        provider.onClosed(1006);
        async.elapse(const Duration(seconds: 5));
        expect(provider.lastCustomSttConfig, same(localConfig));

        provider.dispose();
      });
    });

    for (final endSession in ['close', 'dispose', 'restart']) {
      test('late local availability is ignored after $endSession', () {
        fakeAsync((async) {
          final pending = Completer<CustomSttConfig?>();
          final provider = _CountingSpeechProfileProvider()..pendingLocalConfig = pending;
          provider.usePhoneMic = true;
          provider.updateStartedRecording(true);
          for (var i = 0; i < 3; i++) {
            provider.onClosed(1011);
          }
          async.flushMicrotasks();
          if (endSession == 'dispose') {
            provider.dispose();
          } else {
            provider.close();
            async.flushMicrotasks();
            if (endSession == 'restart') {
              provider.resetTranscript();
              provider.usePhoneMic = true;
              provider.updateStartedRecording(true);
            }
          }
          pending.complete(localConfig);
          async.flushMicrotasks();
          async.elapse(const Duration(seconds: 10));
          expect(provider.usingLocalStt, isFalse);
          expect(provider.openCalls, 0);
          if (endSession != 'dispose') provider.dispose();
        });
      });
    }

    test('repeated close callbacks share one pending availability check', () {
      fakeAsync((async) {
        final pending = Completer<CustomSttConfig?>();
        final provider = _CountingSpeechProfileProvider()..pendingLocalConfig = pending;
        provider.usePhoneMic = true;
        provider.updateStartedRecording(true);
        for (var i = 0; i < 6; i++) {
          provider.onClosed(1011);
        }
        async.flushMicrotasks();
        expect(provider.resolveCalls, 1);
        pending.complete(localConfig);
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 5));
        expect(provider.openCalls, 1);
        provider.dispose();
      });
    });

    test('close() resets the on-device STT mode so it cannot leak into the next session', () async {
      final provider = _CountingSpeechProfileProvider()..localSttConfig = localConfig;
      expect(await provider.enableLocalStt(), isTrue);

      await provider.close();

      expect(provider.usingLocalStt, isFalse);
      provider.dispose();
    });
  });

  // Regression coverage: close() left isInitialised and the STT-unavailable
  // close count untouched, so a stale value from a previous session leaked
  // into the next one — e.g. backing out of a freshly opened Settings page
  // ran active-session cleanup it never started, or a new session tripped
  // STT_UNAVAILABLE one 1011 close earlier than it should have.
  group('close() resets state so a finished session cannot leak into the next', () {
    test('resets isInitialised', () async {
      final provider = SpeechProfileProvider();
      provider.setInitialised(true);

      await provider.close();

      expect(provider.isInitialised, isFalse);
      provider.dispose();
    });

    test('resets the STT-unavailable close count', () async {
      final provider = _CountingSpeechProfileProvider();
      provider.usePhoneMic = true;
      provider.updateStartedRecording(true);

      provider.onClosed(1011);
      provider.onClosed(1011);
      // Two strikes recorded, one away from tripping STT_UNAVAILABLE.

      await provider.close();

      provider.usePhoneMic = true;
      provider.updateStartedRecording(true);
      provider.onClosed(1011);

      expect(
        provider.error,
        'SOCKET_DISCONNECTED',
        reason: 'close() must reset the close count so a new session is not one 1011 away from STT_UNAVAILABLE',
      );

      provider.dispose();
    });
  });

  // Upload failure used to set profileCompleted so All Done appeared, which
  // let people leave onboarding with no voiceprint and made "Completed"
  // telemetry lie. Failure must keep Skip available and must not look like
  // enroll success. Skip (not All Done) is the escape hatch.
  group('upload failure does not pretend the voiceprint landed', () {
    test('does not mark the profile completed after an upload failure', () {
      final provider = SpeechProfileProvider();
      provider.updateStartedRecording(true);

      provider.completeAfterUploadFailure(tooShort: false);

      expect(provider.profileCompleted, isFalse, reason: 'All Done is enroll success, not a failed upload');
      expect(provider.uploadingProfile, isFalse);
      expect(provider.startedRecording, isTrue, reason: 'Skip for now stays on the recording UI');
      expect(provider.error, 'UPLOAD_FAILED');

      provider.dispose();
    });

    test('does not mark the profile completed after a too-short-audio failure', () {
      final provider = SpeechProfileProvider();
      provider.updateStartedRecording(true);

      provider.completeAfterUploadFailure(tooShort: true);

      expect(provider.profileCompleted, isFalse);
      expect(provider.startedRecording, isTrue);
      expect(provider.error, 'TOO_SHORT');

      provider.dispose();
    });
  });

  test('WAV creation failure restores the escape path instead of leaving uploading stuck', () async {
    final provider = SpeechProfileProvider()..audioStorage = _BrokenWavStorage();
    provider.updateStartedRecording(true);
    await provider.finalize();
    expect(provider.uploadingProfile, isFalse);
    expect(provider.profileCompleted, isFalse);
    expect(provider.error, 'UPLOAD_FAILED');
    provider.dispose();
  });

  group('first-run enrollment accepts any topic without punctuation', () {
    test('five seconds of transcribed speech completes after a pause', () {
      fakeAsync((async) {
        final provider = _OnboardingFinalizeProvider();
        provider.updateStartedRecording(true);
        provider.segments.add(_userSegment('1', 'today I walked my dog and enjoyed the sunshine')..end = 5);
        provider.updateSpokenText();
        expect(provider.recordingProgress, 1);
        expect(provider.spokenSentenceCount, 0);
        async.elapse(SpeechProfileProvider.minUploadDuration);
        expect(provider.finalizeCalls, 1);
        async.elapse(SpeechProfileProvider.completionCap);
        expect(provider.finalizeCalls, 1);
        provider.dispose();
      });
    });

    test('silence, Omi prompts, and overlapping spans do not inflate progress', () {
      fakeAsync((async) {
        final provider = _OnboardingFinalizeProvider();
        provider.updateStartedRecording(true);
        provider.segments.addAll([
          _userSegment('q', 'Where do you live?', speakerId: omiSpeakerId)..end = 20,
          _userSegment('1', 'one two')
            ..start = 20
            ..end = 22,
          _userSegment('2', 'three four')
            ..start = 21
            ..end = 23,
          _userSegment('empty', ' ')
            ..start = 23
            ..end = 40,
        ]);
        provider.updateSpokenText();
        expect(provider.recordingProgress, closeTo(0.6, 0.001));
        async.elapse(const Duration(seconds: 30));
        expect(provider.finalizeCalls, 0);
        provider.segments.add(_userSegment('3', 'a little more')
          ..start = 40
          ..end = 42);
        provider.updateSpokenText();
        async.elapse(SpeechProfileProvider.completionGrace);
        expect(provider.finalizeCalls, 1);
        provider.dispose();
      });
    });
  });

  group('speech-profile upload retries transient failures', () {
    test('succeeds on a later attempt without completing on the first failure', () async {
      final provider = _FlakyUploadProvider(failTimes: 2);
      final result = await provider.uploadProfileWithRetry(File('speaker_profile.wav'));

      expect(result.success, isTrue);
      expect(result.tooShort, isFalse);
      expect(provider.uploadAttempts, 3);

      provider.dispose();
    });

    test('does not retry a too-short recording', () async {
      final provider = _FlakyUploadProvider(failTimes: 5, tooShort: true);
      final result = await provider.uploadProfileWithRetry(File('speaker_profile.wav'));

      expect(result.success, isFalse);
      expect(result.tooShort, isTrue);
      expect(provider.uploadAttempts, 1);

      provider.dispose();
    });
  });

  // The recording completes once the user has spoken enough sentences (the
  // UI shows a bar filling toward the target), not when the backend decides
  // the "Answer with your voice" topics were covered.
  group('completes on the spoken sentence target', () {
    test('fills the bar per sentence and finalizes once after a pause at the target', () {
      fakeAsync((async) {
        final provider = _FinalizeCountingProvider();
        provider.updateStartedRecording(true);

        provider.segments.add(_userSegment('1', 'I live in Austin.'));
        provider.updateSpokenText();
        expect(provider.spokenSentenceCount, 1);
        expect(provider.sentenceProgress, closeTo(1 / 3, 0.01));
        expect(provider.finalizeCalls, 0);

        provider.segments.add(_userSegment('2', 'I work on hardware! My goal is 3.5 million users?'));
        provider.updateSpokenText();
        expect(provider.spokenSentenceCount, 3, reason: '"3.5" is not a sentence boundary');
        expect(provider.sentenceProgress, 1.0);
        expect(provider.finalizeCalls, 0, reason: 'the target does not cut the user off mid-sentence');

        async.elapse(SpeechProfileProvider.completionGrace);
        expect(provider.finalizeCalls, 0, reason: 'three short sentences are still below the 5s upload floor');
        async.elapse(SpeechProfileProvider.minUploadDuration - SpeechProfileProvider.completionGrace);
        expect(provider.finalizeCalls, 1, reason: 'finalizes once the user pauses and the upload floor is met');

        provider.segments.add(_userSegment('3', 'And more.'));
        provider.updateSpokenText();
        async.elapse(SpeechProfileProvider.completionCap);
        expect(provider.finalizeCalls, 1, reason: 'later segments must not finalize again');

        provider.dispose();
      });
    });

    test('keeps recording while the user is still talking, up to the cap', () {
      fakeAsync((async) {
        final provider = _FinalizeCountingProvider();
        provider.updateStartedRecording(true);
        provider.segments.add(_userSegment('1', 'One. Two. Three.'));
        provider.updateSpokenText();

        // New speech every second keeps deferring the grace period...
        for (var i = 0; i < 5; i++) {
          async.elapse(const Duration(seconds: 1));
          provider.segments.add(_userSegment('more$i', 'still talking'));
          provider.updateSpokenText();
          expect(provider.finalizeCalls, 0);
        }
        // ...but the cap after the target finalizes regardless.
        async.elapse(SpeechProfileProvider.completionCap);
        expect(provider.finalizeCalls, 1);

        provider.dispose();
      });
    });

    test("ignores Omi's own question segments and the backend's completion event", () {
      final provider = _FinalizeCountingProvider();
      provider.updateStartedRecording(true);

      provider.segments
          .add(_userSegment('q', 'Where do you live? What do you do? Any goals?', speakerId: omiSpeakerId));
      provider.updateSpokenText();
      expect(provider.spokenSentenceCount, 0);
      expect(provider.finalizeCalls, 0);

      provider.onMessageEventReceived(OnboardingCompleteEvent(conversationId: 'c1'));
      expect(provider.finalizeCalls, 0, reason: 'only the sentence target completes the recording');

      provider.dispose();
    });
  });

  // Redo showed the previous recording's words (and counted them toward the
  // target) because nothing cleared the provider's transcript before a new
  // session; initialise() now resets it first.
  group('a new recording starts with an empty transcript', () {
    test('resetTranscript forgets the previous words, progress and completion', () {
      final provider = _FinalizeCountingProvider();
      provider.updateStartedRecording(true);
      fakeAsync((async) {
        provider.segments.add(_userSegment('1', 'I live in Austin. I build hardware. I want to ship!'));
        provider.updateSpokenText();
        async.elapse(SpeechProfileProvider.minUploadDuration);
        expect(provider.finalizeCalls, 1);
        provider.profileCompleted = true;

        provider.resetTranscript();

        expect(provider.text, isEmpty);
        expect(provider.segments, isEmpty);
        expect(provider.sentenceProgress, 0.0);
        expect(provider.profileCompleted, isFalse);

        // The fresh session counts from zero and can finalize again.
        provider.segments.add(_userSegment('2', 'One. Two. Three.'));
        provider.updateSpokenText();
        async.elapse(SpeechProfileProvider.minUploadDuration);
        expect(provider.finalizeCalls, 2);

        provider.dispose();
      });
    });
  });
}
