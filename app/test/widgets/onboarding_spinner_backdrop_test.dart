import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/wrapper.dart';

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
}
