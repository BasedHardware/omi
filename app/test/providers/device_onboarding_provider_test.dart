import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/device_onboarding_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DeviceOnboardingProvider question flow', () {
    test('rapid second tap marks question failed, delayed tap sends question', () async {
      final provider = DeviceOnboardingProvider()..startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isFalse);
      expect(provider.questionFailed, isFalse);

      // Rapid double tap without speaking (< 700ms)
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isFalse);
      expect(provider.questionFailed, isTrue);

      // Retry with speech duration (> 700ms)
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);
      expect(provider.questionFailed, isFalse);

      await Future<void>.delayed(const Duration(milliseconds: 750));
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isTrue);
      expect(provider.questionFailed, isFalse);
    });

    test('onVoiceQuestionFailed resets questionSent and sets questionFailed', () async {
      final provider = DeviceOnboardingProvider()..startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);

      provider.onButtonEvent(1);
      await Future<void>.delayed(const Duration(milliseconds: 750));
      provider.onButtonEvent(1);
      expect(provider.questionSent, isTrue);

      provider.onVoiceQuestionFailed();
      expect(provider.questionSent, isFalse);
      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionFailed, isTrue);

      // Pressing again clears failure and restarts listening
      provider.onButtonEvent(1);
      expect(provider.voiceSessionActive, isTrue);
      expect(provider.questionFailed, isFalse);
    });

    test('onVoiceResponseReceived caches response and question, clears failure', () async {
      final provider = DeviceOnboardingProvider()..startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);

      provider.onButtonEvent(1);
      await Future<void>.delayed(const Duration(milliseconds: 750));
      provider.onButtonEvent(1);
      provider.onVoiceResponseReceived('Omi is an AI wearable', question: 'What is Omi?');

      expect(provider.aiResponse, 'Omi is an AI wearable');
      expect(provider.userQuestion, 'What is Omi?');
      expect(provider.questionFailed, isFalse);
    });

    test('revisiting step from allSetStep returns to allSetStep on advanceStep', () {
      final provider = DeviceOnboardingProvider()..startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.allSetStep);
      expect(provider.currentStep, DeviceOnboardingProvider.allSetStep);

      // Tap to review askQuestionStep
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);
      expect(provider.currentStep, DeviceOnboardingProvider.askQuestionStep);
      expect(provider.returnStep, DeviceOnboardingProvider.allSetStep);

      // Completing the revisited step returns to allSetStep
      provider.advanceStep();
      expect(provider.currentStep, DeviceOnboardingProvider.allSetStep);
      expect(provider.returnStep, isNull);
    });
  });
}
