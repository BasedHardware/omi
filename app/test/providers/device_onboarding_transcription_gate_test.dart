import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/device_onboarding_provider.dart';

import '../support/device_tour_example.dart';

/// The speaking step finishes once the transcript holds enough speech to see transcription work.
bool finishes(String words) {
  final tour = DeviceOnboardingProvider()..startOnboarding();
  tour.onTranscriptSegments([
    TranscriptSegment(
        id: 's0', text: words, speaker: 'SPEAKER_00', isUser: true, personId: null, start: 0, end: 2, translations: []),
  ]);
  final done = tour.transcriptionComplete;
  tour.dispose();
  return done;
}

void main() {
  // Every language's own example has to finish the step: Japanese, Chinese and Thai write a sentence without
  // spaces, and Turkish, Arabic and Tamil say it in four long words.
  for (final locale in AppLocalizations.supportedLocales) {
    test('${locale.toLanguageTag()}: saying the example finishes the speaking step', () {
      final example = deviceTourExample(lookupAppLocalizations(locale).deviceOnboardingTranscriptionSubtitle);
      expect(finishes(example), isTrue, reason: '"$example" should be enough speech');
    });
  }

  // Round-2 review: repeats, bare greetings and bracketed non-speech must not finish the step.
  for (final notSpeech in reviewedNonFinishers) {
    test('"$notSpeech" does not finish the speaking step', () {
      expect(finishes(notSpeech), isFalse);
    });
  }

  test('a greeting is not enough, in any script', () {
    for (final greeting in ['Hello', 'Hi there', 'もしもし', '你好', '안녕하세요', 'สวัสดีครับ', 'Merhaba', 'مرحبا']) {
      expect(finishes(greeting), isFalse, reason: '"$greeting" is not enough speech');
    }
  });

  test('five English words still finish the step, four short ones do not', () {
    expect(finishes('one two three four five'), isTrue);
    expect(finishes('one two three four'), isFalse);
  });
}
