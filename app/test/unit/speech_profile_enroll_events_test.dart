import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/speech_profile_enroll_events.dart';

void main() {
  test('enroll events stay distinct from All Done', () {
    expect(speechProfileEnrollEventName(SpeechProfileEnrollEvent.skipped), 'Speech Profile Skipped');
    expect(
      speechProfileEnrollEventName(SpeechProfileEnrollEvent.uploadSucceeded),
      'Speech Profile Upload Succeeded',
    );
    expect(
      speechProfileEnrollEventName(SpeechProfileEnrollEvent.uploadFailed),
      'Speech Profile Upload Failed',
    );
    expect(
      speechProfileEnrollEventName(SpeechProfileEnrollEvent.embeddingStored),
      'Speech Profile Embedding Stored',
    );
    expect(speechProfileContinuedEventName, 'Onboarding Step Speech Profile Continued');
    expect(speechProfileContinuedEventName.contains('Speech Profile Completed'), isFalse);
  });
}
