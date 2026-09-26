import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/pages/conversation_detail/widgets/feedback_prompt_policy.dart';

void main() {
  test('claims one shared prompt budget and suppresses its target', () async {
    SharedPreferences.setMockInitialValues({});
    final now = DateTime(2026, 9, 22, 10);
    final policy = FeedbackPromptPolicy(sampleFraction: 1, now: () => now, ownerKey: () => 'user-a');

    expect(await policy.canShow('conversation-1'), isTrue);
    expect(await policy.claim('conversation-1'), isTrue);
    expect(await policy.claim('conversation-2'), isFalse);

    final afterCooldown = now.add(FeedbackPromptPolicy.cooldown + const Duration(seconds: 1));
    final cooledDown = FeedbackPromptPolicy(sampleFraction: 1, now: () => afterCooldown, ownerKey: () => 'user-a');
    expect(await cooledDown.canShow('conversation-1'), isTrue);
    await cooledDown.recordDecision('conversation-1');
    expect(await cooledDown.canShow('conversation-1'), isFalse);
  });

  test('malformed state fails closed and sampling is deterministic', () async {
    SharedPreferences.setMockInitialValues({
      'mobile_feedback_prompt_last_exposure_ms_'
          'fc95297aa4f56781': 'bad',
      'mobile_feedback_prompt_suppressed_targets_'
          'fc95297aa4f56781': <String>['conversation-1'],
    });
    final policy = FeedbackPromptPolicy(sampleFraction: 1, ownerKey: () => 'user-a');
    expect(await policy.canShow('conversation-2'), isFalse);

    SharedPreferences.setMockInitialValues({});
    final first = FeedbackPromptPolicy(sampleFraction: 0.5, ownerKey: () => 'user-a');
    final second = FeedbackPromptPolicy(sampleFraction: 0.5, ownerKey: () => 'user-a');
    expect(await first.canShow('conversation-constant'), await second.canShow('conversation-constant'));
  });

  test('fails closed when preferences cannot be loaded', () async {
    Future<SharedPreferences> loader() async => throw StateError('preferences unavailable');
    final policy = FeedbackPromptPolicy(preferencesLoader: loader, ownerKey: () => 'user-a');

    expect(await policy.canShow('conversation-1'), isFalse);
    expect(await policy.claim('conversation-1'), isFalse);
    await expectLater(policy.recordDecision('conversation-1'), completes);
  });

  test('isolates the prompt budget by owner without storing raw identity', () async {
    SharedPreferences.setMockInitialValues({});
    final now = DateTime(2026, 9, 22, 10);
    final userA = FeedbackPromptPolicy(sampleFraction: 1, now: () => now, ownerKey: () => 'user-a');
    final userB = FeedbackPromptPolicy(sampleFraction: 1, now: () => now, ownerKey: () => 'user-b');

    expect(await userA.claim('conversation-1'), isTrue);
    expect(await userA.canShow('conversation-2'), isFalse);
    expect(await userB.canShow('conversation-2'), isTrue);

    final preferences = await SharedPreferences.getInstance();
    expect(preferences.getKeys().any((key) => key.contains('user-a')), isFalse);
    expect(preferences.getKeys().any((key) => key.contains('user-b')), isFalse);
  });

  test('serializes concurrent claims into one shared exposure', () async {
    SharedPreferences.setMockInitialValues({});
    final gate = Completer<void>();
    final preferences = await SharedPreferences.getInstance();
    Future<SharedPreferences> loader() async {
      await gate.future;
      return preferences;
    }

    final policy = FeedbackPromptPolicy(
      preferencesLoader: loader,
      sampleFraction: 1,
      ownerKey: () => 'user-a',
    );

    final first = policy.claim('conversation-1');
    final second = policy.claim('conversation-2');
    gate.complete();

    expect(await first, isTrue);
    expect(await second, isFalse);
  });

  test('missing owner fails closed', () async {
    SharedPreferences.setMockInitialValues({});
    final policy = FeedbackPromptPolicy(sampleFraction: 1, ownerKey: () => null);

    expect(await policy.canShow('conversation-1'), isFalse);
    expect(await policy.claim('conversation-1'), isFalse);
  });

  test('selects one feedback population before mounting prompts', () {
    expect(
      feedbackPromptKindForTarget(targetId: 'conversation-1', hasSummary: true, hasRecording: false),
      FeedbackPromptKind.summary,
    );
    expect(
      feedbackPromptKindForTarget(targetId: 'conversation-1', hasSummary: false, hasRecording: true),
      FeedbackPromptKind.recording,
    );
    final first = feedbackPromptKindForTarget(
      targetId: 'conversation-1',
      hasSummary: true,
      hasRecording: true,
    );
    final second = feedbackPromptKindForTarget(
      targetId: 'conversation-1',
      hasSummary: true,
      hasRecording: true,
    );
    expect(first, isNotNull);
    expect(second, first);
    final populations = [
      for (var index = 0; index < 32; index++)
        feedbackPromptKindForTarget(
          targetId: 'conversation-$index',
          hasSummary: true,
          hasRecording: true,
        ),
    ];
    expect(populations, contains(FeedbackPromptKind.summary));
    expect(populations, contains(FeedbackPromptKind.recording));
    expect(
      feedbackPromptKindForTarget(targetId: 'conversation-1', hasSummary: false, hasRecording: false),
      isNull,
    );
  });
}
