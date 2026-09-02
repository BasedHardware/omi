import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/widgets/onboarding_page_transition.dart';

void main() {
  // Regression: the spinning-dots backdrop used to hide only for the
  // quiet-place intro, then come back as soon as Get Started flipped
  // startedRecording. Speech-profile onboarding is a clean black screen
  // for the whole step — recording state is not part of this decision.
  test('speech-profile onboarding never uses the spinner backdrop', () {
    expect(kOnboardingSpeechProfilePageIndex, 9);
    expect(kOnboardingSpinnerBackdropPages.contains(kOnboardingSpeechProfilePageIndex), isFalse);
    expect(onboardingHidesSpinnerBackdrop(kOnboardingSpeechProfilePageIndex), isTrue);
    expect(onboardingHidesSpinnerBackdrop(5), isFalse);
  });

  test('knowledge graph and complete never bring back the 8-dot spinner', () {
    expect(kOnboardingKnowledgeGraphPageIndex, 10);
    expect(kOnboardingCompletePageIndex, 11);
    expect(kOnboardingSpinnerBackdropPages.contains(kOnboardingKnowledgeGraphPageIndex), isFalse);
    expect(kOnboardingSpinnerBackdropPages.contains(kOnboardingCompletePageIndex), isFalse);
  });

  test('knowledge graph waits for the speech-profile fade-out before fading in', () {
    expect(kOnboardingKnowledgeGraphPageIndex, 10);
    expect(
      onboardingPageEntryDelay(kOnboardingKnowledgeGraphPageIndex),
      kOnboardingPageFadeDuration,
    );
    expect(onboardingPageEntryDelay(kOnboardingSpeechProfilePageIndex).inMilliseconds, greaterThan(400));
    expect(onboardingPageEntryDelay(3), Duration.zero);
  });

  test('complete waits for the knowledge-graph fade-out before fading in', () {
    expect(
      onboardingPageEntryDelay(kOnboardingCompletePageIndex),
      kOnboardingPageFadeDuration,
    );
  });
}
