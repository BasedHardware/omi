import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import '../providers/guided_voice_controller_test.dart' show FakeVoiceIO;

void main() {
  group('Onboarding voice retention & goal idempotency (#20785)', () {
    test('goal idempotency key is stable across sessions for the same account', () async {
      // Session 1: User runs guided voice introduction for account 'test-user-42'
      final io1 = FakeVoiceIO();
      final flow1 = GuidedVoiceController(io1, accountUid: 'test-user-42');
      for (var i = 0; i < 4; i++) {
        io1.text = i == 3 ? 'Right now my goal is to ship Omi.' : 'Personal detail $i';
        await flow1.startRecording();
        io1.speak();
      }
      expect(flow1.answers.length, 4);
      expect(flow1.answers.last.isGoal, isTrue);
      final goalKey1 = flow1.answers.last.id;
      expect(goalKey1, 'intro-goal-test-user-42');

      await flow1.saveAll();
      expect(io1.goals, ['Ship Omi']);
      expect(io1.goalKeys.first, 'intro-goal-test-user-42');

      // Session 2: If flow is recreated or relaunched for the same account,
      // the goal idempotency key must be identical to prevent duplicate goals on backend.
      final io2 = FakeVoiceIO();
      final flow2 = GuidedVoiceController(io2, accountUid: 'test-user-42');
      for (var i = 0; i < 4; i++) {
        io2.text = i == 3 ? 'Right now my goal is to ship Omi.' : 'Personal detail $i';
        await flow2.startRecording();
        io2.speak();
      }
      expect(flow2.answers.length, 4);
      expect(flow2.answers.last.isGoal, isTrue);
      final goalKey2 = flow2.answers.last.id;
      expect(goalKey2, goalKey1);

      await flow2.saveAll();
      expect(io2.goals, ['Ship Omi']);
      expect(io2.goalKeys.first, io1.goalKeys.first);
    });

    test('completed voice introduction retains answers and done stage when controller is kept', () async {
      final io = FakeVoiceIO();
      final flow = GuidedVoiceController(io, accountUid: 'user-abc');

      for (var i = 0; i < 4; i++) {
        io.text = i == 3 ? 'My primary goal is to build great AI.' : 'Memory fact $i';
        await flow.startRecording();
        io.speak();
      }
      await flow.saveAll();

      expect(flow.stage, IntroductionStage.done);
      expect(flow.answers.length, 4);
      expect(flow.goalSaved, isTrue);

      // Simulating navigating back from graph: when wrapper retains flow,
      // stage remains done and answers remain intact without re-prompting or double-saving.
      expect(flow.answers.any((a) => a.isGoal && a.saved), isTrue);
      expect(flow.answers.where((a) => !a.isGoal && a.saved).length, 3);
    });

    test('wrapper marks setup and complete pages as resumable steps', () {
      // kAuthPage (0) and kAiConsentPage (1) are pre-onboarding gates and must not be resumable
      expect(OnboardingWrapper.isResumableStepForTesting(0), isFalse);
      expect(OnboardingWrapper.isResumableStepForTesting(1), isFalse);

      // Steps from kNamePage (2) through kCompletePage (9) must be resumable
      expect(OnboardingWrapper.isResumableStepForTesting(2), isTrue); // kNamePage
      expect(OnboardingWrapper.isResumableStepForTesting(6), isTrue); // kSpeechProfilePage
      expect(OnboardingWrapper.isResumableStepForTesting(7), isTrue); // kKnowledgeGraphPage
      expect(OnboardingWrapper.isResumableStepForTesting(8), isTrue); // kSetupPage
      expect(OnboardingWrapper.isResumableStepForTesting(9), isTrue); // kCompletePage
    });

    test('wrapper previousStep correctly navigates back from complete, setup, and graph', () {
      // From Complete page (9):
      // When setup page is enabled: returns Setup page (8)
      expect(
        OnboardingWrapper.previousStepForTesting(
          currentIndex: 9,
          setupPageEnabled: true,
          knowledgeGraphStepEnabled: false,
        ),
        8,
      );

      // When setup page is disabled and graph is enabled: returns Graph page (7)
      expect(
        OnboardingWrapper.previousStepForTesting(
          currentIndex: 9,
          setupPageEnabled: false,
          knowledgeGraphStepEnabled: true,
        ),
        7,
      );

      // When setup and graph are disabled: returns Speech profile page (6)
      expect(
        OnboardingWrapper.previousStepForTesting(
          currentIndex: 9,
          setupPageEnabled: false,
          knowledgeGraphStepEnabled: false,
        ),
        6,
      );

      // From Setup page (8):
      // Returns graph (7) if graph enabled, else speech profile (6)
      expect(
        OnboardingWrapper.previousStepForTesting(
          currentIndex: 8,
          setupPageEnabled: true,
          knowledgeGraphStepEnabled: true,
        ),
        7,
      );
      expect(
        OnboardingWrapper.previousStepForTesting(
          currentIndex: 8,
          setupPageEnabled: true,
          knowledgeGraphStepEnabled: false,
        ),
        6,
      );

      // From Knowledge Graph page (7): returns speech profile (6)
      expect(
        OnboardingWrapper.previousStepForTesting(
          currentIndex: 7,
          setupPageEnabled: false,
          knowledgeGraphStepEnabled: true,
        ),
        6,
      );
    });
  });
}
