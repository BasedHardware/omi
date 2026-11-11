import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/services/experiments/onboarding_setup_rating_prompt.dart';

// The setup page is flag-gated and fail-closed: off, slow, missing or erroring flag reads all
// leave the onboarding flow exactly as it was (knowledge graph -> completion screen).

void main() {
  test('flag key is the registered PostHog key', () {
    expect(OnboardingSetupRatingPromptGate.enabledFlag, 'onboarding-setup-rating-prompt');
  });

  test('no debug override in an ordinary test build', () {
    expect(OnboardingSetupRatingPromptGate.debugOverrideActive, isFalse);
  });

  test('flag off -> disabled', () async {
    final keys = <String>[];
    final enabled = await OnboardingSetupRatingPromptGate.isEnabled(readFlag: (key) async {
      keys.add(key);
      return false;
    });
    expect(enabled, isFalse);
    expect(keys, ['onboarding-setup-rating-prompt']);
  });

  test('flag on -> enabled', () async {
    expect(await OnboardingSetupRatingPromptGate.isEnabled(readFlag: (_) async => true), isTrue);
  });

  test('flag read error -> disabled (fail closed)', () async {
    expect(
      await OnboardingSetupRatingPromptGate.isEnabled(readFlag: (_) => Future.error(StateError('no sdk'))),
      isFalse,
    );
  });

  test('flag off skips the setup page: knowledge graph goes straight to the completion screen', () {
    expect(
      OnboardingProgressStepsForTest.stepAfterKnowledgeGraph(setupPageEnabled: false),
      OnboardingProgressStepsForTest.completePage,
    );
    expect(
      OnboardingProgressStepsForTest.stepAfterKnowledgeGraph(setupPageEnabled: true),
      OnboardingProgressStepsForTest.setupPage,
    );
    expect(OnboardingProgressStepsForTest.steps, isNot(contains(OnboardingProgressStepsForTest.setupPage)),
        reason: 'the setup page is transitional: no progress dot, no back, not a resume point');
  });
}
