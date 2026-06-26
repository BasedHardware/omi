import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/models/stt_result.dart';

void main() {
  group('SttTranscriptionResult', () {
    test('preserves TranscriptSegment-compatible metadata by default', () {
      final result = SttTranscriptionResult.fromJsonWithSchema({
        'segments': [
          {
            'text': 'hello',
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': true,
            'person_id': 'user-person',
            'start': 0.0,
            'end': 1.0,
            'translations': [
              {'lang': 'es', 'text': 'hola'},
            ],
          },
          {
            'text': 'there',
            'speaker': 'SPEAKER_01',
            'speaker_id': 1,
            'is_user': false,
            'person_id': 'other-person',
            'start': 1.0,
            'end': 2.0,
          },
        ],
      }, const SttResponseSchema());

      expect(result.segments, hasLength(2));

      final first = result.segments.first.toTranscriptSegmentJson();
      expect(first['speaker'], 'SPEAKER_00');
      expect(first['speaker_id'], 0);
      expect(first['is_user'], true);
      expect(first['person_id'], 'user-person');
      expect(first['translations'], [
        {'lang': 'es', 'text': 'hola'},
      ]);

      final second = result.segments.last.toTranscriptSegmentJson();
      expect(second['speaker'], 'SPEAKER_01');
      expect(second['speaker_id'], 1);
      expect(second['is_user'], false);
      expect(second['person_id'], 'other-person');
    });

    test('supports explicit metadata field mappings', () {
      final result = SttTranscriptionResult.fromJsonWithSchema(
        {
          'items': [
            {
              'word': 'mapped',
              'times': {'start': 4.0, 'end': 5.5},
              'speaker_meta': {'label': 'SPEAKER_07', 'id': 7},
              'owner': {'is_user': 'true', 'person': 'person-7'},
            },
          ],
        },
        const SttResponseSchema(
          segmentsPath: 'items',
          segmentsTextField: 'word',
          segmentsStartField: 'times.start',
          segmentsEndField: 'times.end',
          segmentsSpeakerField: 'speaker_meta.label',
          segmentsSpeakerIdField: 'speaker_meta.id',
          segmentsIsUserField: 'owner.is_user',
          segmentsPersonIdField: 'owner.person',
        ),
      );

      final segment = result.segments.single;
      expect(segment.text, 'mapped');
      expect(segment.start, 4.0);
      expect(segment.end, 5.5);
      expect(segment.speaker, 'SPEAKER_07');
      expect(segment.speakerId, 7);
      expect(segment.isUser, true);
      expect(segment.personId, 'person-7');
    });

    test('derives speaker label from speaker id when no label is present', () {
      final result = SttTranscriptionResult.fromJsonWithSchema({
        'segments': [
          {'text': 'numbered', 'speaker_id': 3, 'start': 1.0, 'end': 2.0},
        ],
      }, const SttResponseSchema());

      final segment = result.segments.single;
      expect(segment.speakerId, 3);
      expect(segment.speaker, 'SPEAKER_3');
    });

    test('merges adjacent transcript segments only when speaker identity matches', () {
      final merged = mergeTranscriptSegmentsBySpeaker([
        SttSegment(text: 'same', start: 0, end: 1, speaker: 'Participant', speakerId: 1),
        SttSegment(text: 'speaker', start: 1, end: 2, speaker: 'Participant', speakerId: 1),
        SttSegment(text: 'different id', start: 2, end: 3, speaker: 'Participant', speakerId: 2),
      ]);

      expect(merged, hasLength(2));
      expect(merged.first['text'], 'same speaker');
      expect(merged.first['speaker_id'], 1);
      expect(merged.last['text'], 'different id');
      expect(merged.last['speaker_id'], 2);
    });
  });
}
