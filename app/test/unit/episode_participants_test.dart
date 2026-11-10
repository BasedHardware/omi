import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/ui/ui.dart';

TranscriptSegment _segment(String id, {bool user = false, int speaker = 1, String? person}) => TranscriptSegment(
      id: id,
      text: 'line $id',
      speaker: 'SPEAKER_${user ? 0 : speaker}',
      isUser: user,
      personId: person,
      translations: [],
      start: 0,
      end: 1,
    );

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));
  final maya = Person(id: 'maya', name: 'Maya', createdAt: DateTime(2026), updatedAt: DateTime(2026));

  test('the header names exactly the speakers the transcript names', () {
    final segments = [
      _segment('a', user: true),
      _segment('b', person: 'maya'),
      _segment('c', speaker: 2),
      _segment('d', person: 'maya'),
    ];
    final names = SpeakerNames.forSegments(segments, people: [maya], l10n: l10n);
    final participants = EpisodePresentation.participants(segments, [maya], l10n);
    expect(participants, ['You', 'Maya']);
    // Every name in the header is the label the transcript prints for that speaker.
    for (final name in participants) {
      expect(segments.map((s) => names.forSegment(s)), contains(name));
    }
    expect(participants, isNot(contains(names.forSegment(segments[2]))), reason: 'Speaker 2 is unresolved');
  });

  test('an unresolved speaker is never named, even if a person id points nowhere', () {
    final segments = [_segment('a', user: true), _segment('b', person: 'ghost')];
    expect(EpisodePresentation.participants(segments, [maya], l10n), ['You']);
  });
}
