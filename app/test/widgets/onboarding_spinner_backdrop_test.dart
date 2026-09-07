import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/wrapper.dart';

void main() {
  // Regression: the 8-dot spinner used to burst/blink on the way to the
  // completion screen. "You are all set" is a clean black screen, and the
  // retired speech-profile / memory-graph indices between permissions and
  // complete must never bring the spinner back either.
  test('complete and the retired placeholder steps never use the spinner backdrop', () {
    expect(kOnboardingCompletePageIndex, 11);
    expect(kOnboardingSpinnerBackdropPages.contains(kOnboardingCompletePageIndex), isFalse);
    expect(kOnboardingSpinnerBackdropPages.contains(9), isFalse);
    expect(kOnboardingSpinnerBackdropPages.contains(10), isFalse);
    expect(kOnboardingSpinnerBackdropPages.contains(5), isTrue);
  });

  test('complete waits for the spinner to leave before fading in', () {
    const spinnerFade = Duration(milliseconds: 1200);
    expect(onboardingPageEntryDelay(kOnboardingCompletePageIndex, spinnerFade: spinnerFade), spinnerFade);
    expect(onboardingPageEntryDelay(3, spinnerFade: spinnerFade), Duration.zero);
    expect(onboardingPageEntryDelay(5, spinnerFade: spinnerFade), Duration.zero);
  });
}
