import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import '../providers/guided_voice_controller_test.dart' show FakeVoiceIO;

Future<void> _answerAll(FakeVoiceIO io, GuidedVoiceController flow,
    {required String goal, required String memory}) async {
  await flow.start();
  for (var i = 0; i < 4; i++) {
    io.text = i == 3 ? goal : '$memory $i';
    io.speak();
    await flow.next();
    expect(flow.stage, IntroductionStage.confirmation);
    await flow.confirmAnswer();
  }
}

void main() {
  group('Onboarding voice retention & goal idempotency (#20785)', () {
    test('goal idempotency key is stable across sessions for the same account', () async {
      // Session 1: User runs guided voice introduction for account 'test-user-42'
      final io1 = FakeVoiceIO();
      final flow1 = GuidedVoiceController(io1, accountUid: 'test-user-42');
      addTearDown(flow1.dispose);
      await _answerAll(io1, flow1, goal: 'Right now my goal is to ship Omi.', memory: 'Personal detail');
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
      addTearDown(flow2.dispose);
      await _answerAll(io2, flow2, goal: 'Right now my goal is to ship Omi.', memory: 'Personal detail');
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
      addTearDown(flow.dispose);

      await _answerAll(io, flow, goal: 'My primary goal is to build great AI.', memory: 'Memory fact');
      await flow.saveAll();

      expect(flow.stage, IntroductionStage.done);
      expect(flow.answers.length, 4);
      expect(flow.goalSaved, isTrue);

      // Simulating navigating back from graph: when wrapper retains flow,
      // stage remains done and answers remain intact without re-prompting or double-saving.
      expect(flow.answers.any((a) => a.isGoal && a.saved), isTrue);
      expect(flow.answers.where((a) => !a.isGoal && a.saved).length, 3);
    });
  });
}
