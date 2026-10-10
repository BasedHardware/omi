import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/device_onboarding_provider.dart';

void main() {
  group('DeviceOnboardingProvider voice question timeout and auto-submit (#20786)', () {
    late DeviceOnboardingProvider provider;

    setUp(() {
      provider = DeviceOnboardingProvider();
      provider.startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);
    });

    tearDown(() {
      provider.dispose();
    });

    test('single button press activates voice session', () {
      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isFalse);

      provider.onButtonEvent(1);

      expect(provider.voiceSessionActive, isTrue);
      expect(provider.questionSent, isFalse);
    });

    test('second button press marks questionSent and ends voice session', () {
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);

      provider.onButtonEvent(1);

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isTrue);
    });

    test('onQuestionSubmitted marks questionSent when user does not press second time', () {
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);
      expect(provider.questionSent, isFalse);

      // Simulates the 15s timeout from capture service submitting the question
      provider.onQuestionSubmitted();

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isTrue);
    });

    test('onVoiceResponseReceived updates aiResponse and clears active session', () {
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);

      provider.onVoiceResponseReceived('Omi reply test');

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isTrue);
      expect(provider.aiResponse, equals('Omi reply test'));
    });

    test('resetting onboarding cancels active voice session and timers', () {
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);

      provider.startOnboarding();

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isFalse);
      expect(provider.aiResponse, isNull);
    });
  });
}
