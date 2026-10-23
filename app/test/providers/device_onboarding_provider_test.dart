import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

void main() {
  group('DeviceOnboardingProvider - ask question step', () {
    late DeviceOnboardingProvider provider;

    setUp(() {
      provider = DeviceOnboardingProvider();
      provider.startOnboarding();
      provider.goToStep(DeviceOnboardingProvider.askQuestionStep);
    });

    tearDown(() {
      if (!provider.isDisposed) {
        provider.dispose();
      }
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
      expect(provider.questionFailure, VoiceQuestionFailure.noSpeech);
    });

    test('pressing again after a failure clears the retry hint and starts listening', () {
      provider.onButtonEvent(1);
      provider.onButtonEvent(1);
      provider.onVoiceQuestionFailed();
      expect(provider.questionFailed, isTrue);

      provider.onButtonEvent(1); // retry press

      expect(provider.questionFailed, isFalse);
      expect(provider.questionFailure, isNull);
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

    test('overlapping single-press while questionSent is pending does not restart listening (#23385)', () {
      provider.onButtonEvent(1);
      provider.onButtonEvent(1);
      expect(provider.questionSent, isTrue);
      expect(provider.canStartQuestionAttempt, isFalse);

      provider.onButtonEvent(1);

      expect(provider.voiceSessionActive, isFalse);
      expect(provider.questionSent, isTrue);
    });

    test('stale attempt callbacks cannot overwrite a newer tutorial question attempt (#23385)', () {
      final firstAttempt = provider.onVoiceQuestionListeningStarted();
      provider.onVoiceQuestionSubmitted(attemptId: firstAttempt);
      provider.onVoiceQuestionFailed(failure: VoiceQuestionFailure.timeout, attemptId: firstAttempt);

      final secondAttempt = provider.onVoiceQuestionListeningStarted();
      provider.onVoiceQuestionSubmitted(attemptId: secondAttempt);

      // Late callbacks from the first attempt must be ignored.
      provider.onVoiceQuestionTranscribed('stale question', attemptId: firstAttempt);
      provider.onVoiceResponseReceived('stale answer', attemptId: firstAttempt);
      provider.onVoiceQuestionFailed(failure: VoiceQuestionFailure.server, attemptId: firstAttempt);

      expect(provider.questionSent, isTrue);
      expect(provider.userQuestion, isNull);
      expect(provider.aiResponse, isNull);
      expect(provider.questionFailed, isFalse);

      provider.onVoiceResponseReceived(
        'fresh answer',
        question: 'fresh question',
        attemptId: secondAttempt,
      );
      expect(provider.userQuestion, 'fresh question');
      expect(provider.aiResponse, 'fresh answer');
    });

    test('pending tutorial question times out to a retryable failure instead of stalling forever (#23385)', () async {
      final timedProvider = DeviceOnboardingProvider(
        questionPendingTimeout: const Duration(milliseconds: 20),
      );
      addTearDown(() {
        if (!timedProvider.isDisposed) timedProvider.dispose();
      });
      timedProvider.startOnboarding();
      timedProvider.goToStep(DeviceOnboardingProvider.askQuestionStep);

      timedProvider.onVoiceQuestionListeningStarted();
      timedProvider.onVoiceQuestionSubmitted();
      expect(timedProvider.questionSent, isTrue);

      await Future<void>.delayed(const Duration(milliseconds: 50));

      expect(timedProvider.questionSent, isFalse);
      expect(timedProvider.questionFailed, isTrue);
      expect(timedProvider.questionFailure, VoiceQuestionFailure.timeout);
      expect(timedProvider.canStartQuestionAttempt, isTrue);
    });
  });
}
