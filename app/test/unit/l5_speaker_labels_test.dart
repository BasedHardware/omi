import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/speaker_suggestions.dart';

TranscriptSegment segment(String id, {String? source}) => TranscriptSegment(
      id: id,
      text: 'synthetic',
      speaker: 'SPEAKER_01',
      isUser: false,
      personId: source == 'manual' ? 'person' : null,
      speakerLabelSource: source,
      start: 0,
      end: 1,
      translations: [],
    );
SpeakerLabelSuggestionEvent event({
  bool? isUser,
  String person = '',
  bool retracted = false,
}) =>
    SpeakerLabelSuggestionEvent(
      speakerId: 1,
      segmentId: 'a',
      personId: person,
      personName: retracted ? '' : 'Synthetic',
      isUser: isUser,
      retracted: retracted,
    );
void main() {
  test('explicit owner is authoritative, sentinel is a legacy fallback', () {
    expect(event(isUser: true).resolvesOwner, isTrue);
    expect(event(person: 'user').resolvesOwner, isTrue);
    expect(event(isUser: false, person: 'user').resolvesOwner, isFalse);
    final wire = SpeakerLabelSuggestionEvent.fromJson({
      'speaker_id': 1,
      'segment_id': 'a',
      'person_id': '',
      'person_name': '',
      'is_user': true,
    });
    expect(wire.resolvesOwner, isTrue);
    expect(wire.speakerId, 1);
  });
  test(
    'a retraction removes pending suggestions without clearing existing labels',
    () {
      final segments = [
        segment('a')..isUser = true,
        segment('b', source: 'manual'),
      ];
      final suggestions = {'a': event()};
      expect(
        reconcileSpeakerSuggestion(
          event(retracted: true),
          segments,
          [],
          suggestions,
        ),
        SpeakerSuggestionDisposition.retained,
      );
      expect(suggestions, isEmpty);
      expect(segments.first.isUser, isTrue);
      expect(segments.last.personId, 'person');
    },
  );
  test(
    'a named suggestion cannot replace a local assignment or an in-progress edit',
    () {
      final segments = [segment('a', source: 'manual')];
      expect(
        reconcileSpeakerSuggestion(event(person: 'resolved'), segments, [], {}),
        SpeakerSuggestionDisposition.ignored,
      );
      expect(
        reconcileSpeakerSuggestion(
          event(person: 'resolved'),
          [segment('a')],
          ['a'],
          {},
        ),
        SpeakerSuggestionDisposition.ignored,
      );
      expect(
        reconcileSpeakerSuggestion(
          event(person: 'resolved'),
          [segment('a')],
          [],
          {},
        ),
        SpeakerSuggestionDisposition.assignment,
      );
    },
  );
}
