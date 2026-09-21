import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

TranscriptSegment decode(String id, {int? speakerId, String speaker = 'SPEAKER_00'}) => TranscriptSegment.fromJson({
      'id': id,
      'text': 'Synthetic speech',
      'speaker': speaker,
      'speaker_id': speakerId,
      'is_user': false,
      'start': 0.0,
      'end': 10.0,
    });

void main() {
  test('explicit canonical identity wins, including zero, and round trips', () {
    for (final id in [0, 2, 7]) {
      final segment = decode('a', speakerId: id, speaker: 'SPEAKER_03');
      expect(segment.speakerId, id);
      expect(TranscriptSegment.fromJson(segment.toJson()).speakerId, id);
      expect(segment.speaker, 'SPEAKER_03');
    }
    expect(decode('legacy', speaker: 'SPEAKER_03').speakerId, 3);
    expect(decode('unknown', speaker: 'unknown').speakerId, 0);
  });

  test('updates preserve independent speakers with the same provider label', () {
    final segments = [decode('a', speakerId: 0), decode('b', speakerId: 2)];
    final incoming = [decode('b', speakerId: 2), decode('c', speakerId: 7)];
    segments.addAll(TranscriptSegment.updateSegments(segments, incoming));
    expect(segments.map((s) => s.speakerId), [0, 2, 7]);
    expect(TranscriptSegment.getDisplaySpeakerId(2, segments), 3);
    segments.first.isUser = true;
    expect(TranscriptSegment.getDisplaySpeakerId(2, segments), 3);
  });
}
