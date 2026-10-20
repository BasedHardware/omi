import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/device_onboarding_provider.dart';

void main() {
  group('DeviceOnboardingProvider - ask question step', () {
    late DeviceOnboardingProvider provider;

    setUp(() {
      provider = DeviceOnboardingProvider();
      provider.startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);
    });

    test('first press starts listening', () {
      provider.onButtonEvent(1);

      expect(provider.voiceSessionActive, isTrue);
      expect(provider.questionSent, isFalse);
      expect(provider.questionFailed, isFalse);
    });

    test('second press marks the question sent and stops listening', () {
      provider.onButtonEvent(1); // first press
      provider.onButtonEvent(1); // second press

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isTrue);
    });

    test('press, stay silent, press again leaves the step stuck on processing without the fix', () {
      provider.onButtonEvent(1);
      provider.onButtonEvent(1);
      expect(provider.questionSent, isTrue, reason: 'processing spinner would show indefinitely');

      // Capture reports no audio was ever captured for the session (emptyFrames).
      provider.onVoiceQuestionFailed();

      expect(provider.questionSent, isFalse);
      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionFailed, isTrue, reason: 'the step should offer a retry hint instead of spinning forever');
    });

    test('a no-speech server reply resets the step the same way as dropped empty frames', () {
      provider.onButtonEvent(1);
      provider.onButtonEvent(1);

      provider.onVoiceQuestionFailed();

      expect(provider.questionFailed, isTrue);
    });

    test('pressing again after a failure clears the retry hint and starts listening', () {
      provider.onButtonEvent(1);
      provider.onButtonEvent(1);
      provider.onVoiceQuestionFailed();
      expect(provider.questionFailed, isTrue);

      provider.onButtonEvent(1); // retry press

      expect(provider.questionFailed, isFalse);
      expect(provider.voiceSessionActive, isTrue);
    });

    test('a failure signal arriving after a real answer never clobbers the answer', () {
      provider.onButtonEvent(1);
      provider.onButtonEvent(1);
      provider.onVoiceResponseReceived('42');
      expect(provider.aiResponse, '42');

      // A stale/late failure callback must not undo a response that already arrived.
      provider.onVoiceQuestionFailed();

      expect(provider.aiResponse, '42');
      expect(provider.questionFailed, isFalse);
    });

    test('a failure signal outside the ask-question step is ignored', () {
      provider.goToStep(DeviceOnboardingProvider.powerCycleStep);

      provider.onVoiceQuestionFailed();

      expect(provider.questionFailed, isFalse);
    });
  });
}
