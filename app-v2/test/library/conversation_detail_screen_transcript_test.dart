import 'package:flutter_test/flutter_test.dart';
import 'package:nooto_v2/library/conversation_detail_screen.dart';

/// Speaker grouping is the load-bearing transcript fix. These tests pin
/// the boundary rules so a future refactor doesn't silently re-explode
/// every utterance into its own row.
void main() {
  group('groupConsecutiveSegmentsBySpeaker', () {
    test('returns empty list for empty input', () {
      expect(groupConsecutiveSegmentsBySpeaker(const []), isEmpty);
    });

    test('groups consecutive same-speaker segments into one block', () {
      final out = groupConsecutiveSegmentsBySpeaker([
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'a'},
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'b'},
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'c'},
      ]);
      expect(out.length, 1);
      expect(out.first.length, 3);
    });

    test('starts a new group when is_user flips', () {
      final out = groupConsecutiveSegmentsBySpeaker([
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'me'},
        {'is_user': false, 'speaker': 'SPEAKER_1', 'text': 'them'},
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'me again'},
      ]);
      expect(out.length, 3);
    });

    test('starts a new group when speaker label changes (same is_user)', () {
      final out = groupConsecutiveSegmentsBySpeaker([
        {'is_user': false, 'speaker': 'SPEAKER_1', 'text': 'a'},
        {'is_user': false, 'speaker': 'SPEAKER_2', 'text': 'b'},
      ]);
      expect(out.length, 2);
    });

    test('matches the screenshot scenario — 8 same-speaker rows collapse to 1 block', () {
      final repeats = List.generate(
        8,
        (i) => {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'line $i'},
      );
      final out = groupConsecutiveSegmentsBySpeaker(repeats);
      expect(out.length, 1);
      expect(out.first.length, 8);
    });

    test('handles a typical two-speaker back-and-forth', () {
      final out = groupConsecutiveSegmentsBySpeaker([
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'hi'},
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'how are you'},
        {'is_user': false, 'speaker': 'SPEAKER_1', 'text': 'good'},
        {'is_user': false, 'speaker': 'SPEAKER_1', 'text': 'and you'},
        {'is_user': true, 'speaker': 'SPEAKER_0', 'text': 'fine'},
      ]);
      expect(out.length, 3);
      expect(out[0].length, 2);
      expect(out[1].length, 2);
      expect(out[2].length, 1);
    });
  });
}
