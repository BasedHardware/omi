import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/omi_button_action.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/services.dart';

/// Records which heavyweight effects the button dispatcher asked for instead
/// of running them (network processing, BLE pause/resume).
class _RecordingCaptureProvider extends CaptureProvider {
  int endConversationCalls = 0;
  int pauseCalls = 0;
  int resumeCalls = 0;

  @override
  Future<void> forceProcessingCurrentConversation() async {
    endConversationCalls++;
  }

  @override
  Future<void> pauseDeviceRecording() async {
    pauseCalls++;
  }

  @override
  Future<void> resumeDeviceRecording() async {
    resumeCalls++;
  }
}

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
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

const _deviceId = 'omi-test-device';

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
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
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  Future<_RecordingCaptureProvider> providerWith(Map<String, Object> prefs) async {
    SharedPreferences.setMockInitialValues(prefs);
    await SharedPreferencesUtil.init();
    final provider = _RecordingCaptureProvider();
    addTearDown(provider.dispose);
    return provider;
  }

  group('default mapping', () {
    test('single tap toggles the ask-a-question session', () async {
      final provider = await providerWith({});

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.singleTap);
      expect(provider.isVoiceQuestionSessionActive, isTrue);

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.singleTap);
      expect(provider.isVoiceQuestionSessionActive, isFalse);
    });

    test('double tap mutes, then unmutes, without overlapping requests', () async {
      final provider = await providerWith({});

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.doubleTap);
      expect(provider.pauseCalls, 1);
      // The stub pause completes on a later microtask; a second tap before then is dropped.
      provider.handleDeviceButtonState(_deviceId, OmiButtonState.doubleTap);
      expect(provider.pauseCalls, 1);
      expect(provider.resumeCalls, 0);
    });

    test('triple tap ends the conversation', () async {
      final provider = await providerWith({});

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.tripleTap);

      expect(provider.endConversationCalls, 1);
      expect(provider.isVoiceQuestionSessionActive, isFalse);
    });
  });

  group('remapped gestures', () {
    test('double tap runs the persisted star action and toggles it back off', () async {
      final provider = await providerWith({'doubleTapAction': OmiButtonAction.starConversation.storedValue});

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.doubleTap);
      expect(provider.isConversationMarkedForStarring, isTrue);

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.doubleTap);
      expect(provider.isConversationMarkedForStarring, isFalse);
      expect(provider.pauseCalls, 0);
    });

    test('ask a question can live on the triple tap', () async {
      final provider = await providerWith({
        'tripleTapAction': OmiButtonAction.askQuestion.storedValue,
        'singleTapAction': OmiButtonAction.endConversation.storedValue,
      });

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.tripleTap);
      expect(provider.isVoiceQuestionSessionActive, isTrue);
      expect(provider.endConversationCalls, 0);

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.singleTap);
      expect(provider.endConversationCalls, 1);
    });

    test('"do nothing" swallows the gesture', () async {
      final provider = await providerWith({'singleTapAction': OmiButtonAction.none.storedValue});

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.singleTap);

      expect(provider.isVoiceQuestionSessionActive, isFalse);
      expect(provider.endConversationCalls, 0);
      expect(provider.pauseCalls, 0);
      expect(provider.isConversationMarkedForStarring, isFalse);
    });
  });

  group('legacy firmware hold-to-talk', () {
    test('3 starts a question and 5 sends it', () async {
      final provider = await providerWith({});

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.longPress);
      expect(provider.isVoiceQuestionSessionActive, isTrue);

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.release);
      expect(provider.isVoiceQuestionSessionActive, isFalse);
    });
  });

  group('interactive onboarding', () {
    test('step 1 runs ask-a-question even when single tap is mapped elsewhere', () async {
      final provider = await providerWith({'singleTapAction': OmiButtonAction.endConversation.storedValue});
      final onboarding = DeviceOnboardingProvider()..startOnboarding();
      addTearDown(onboarding.dispose);
      onboarding.advanceStep(); // step 1: ask a question
      provider.deviceOnboardingProvider = onboarding;

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.singleTap);

      expect(provider.isVoiceQuestionSessionActive, isTrue);
      expect(onboarding.voiceSessionActive, isTrue);
      expect(provider.endConversationCalls, 0);
    });

    test('other steps keep gestures away from the user mapping', () async {
      final provider = await providerWith({});
      final onboarding = DeviceOnboardingProvider()..startOnboarding();
      addTearDown(onboarding.dispose);
      provider.deviceOnboardingProvider = onboarding; // step 0: transcription demo

      provider.handleDeviceButtonState(_deviceId, OmiButtonState.tripleTap);
      provider.handleDeviceButtonState(_deviceId, OmiButtonState.doubleTap);

      expect(provider.endConversationCalls, 0);
      expect(provider.pauseCalls, 0);
    });
  });
}
