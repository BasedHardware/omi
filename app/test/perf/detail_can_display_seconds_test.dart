import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

// The pairwise definition canDisplaySeconds replaced (O(n²) on detail open).
bool _pairwise(List<TranscriptSegment> s) {
  for (var i = 0; i < s.length; i++) {
    for (var j = i + 1; j < s.length; j++) {
      if (s[i].start > s[j].end || s[i].end > s[j].start) return false;
    }
  }
  return true;
}

TranscriptSegment _segment(int i, double start, double end) => TranscriptSegment(
      id: 's$i',
      text: 'line $i',
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: start,
      end: end,
      translations: const [],
    );

void main() {
  test('one-pass canDisplaySeconds matches the pairwise definition', () {
    final random = Random(23);
    const specials = [double.nan, double.infinity, double.negativeInfinity, 0.0];
    double value(double base) => random.nextInt(20) == 0 ? specials[random.nextInt(specials.length)] : base;
    for (var trial = 0; trial < 3000; trial++) {
      final n = random.nextInt(12);
      var t = 0.0;
      final segments = <TranscriptSegment>[];
      for (var i = 0; i < n; i++) {
        // Mostly ordered, sometimes overlapping or out of order.
        t += random.nextDouble() * 4 - (random.nextInt(6) == 0 ? 5 : 0);
        segments.add(_segment(i, value(t), value(t + random.nextDouble() * 3)));
      }
      expect(TranscriptSegment.canDisplaySeconds(segments), _pairwise(segments), reason: 'trial $trial: $segments');
    }
    final ordered = [for (var i = 0; i < 1200; i++) _segment(i, i * 2.0, i * 2.0 + 1.5)];
    expect(TranscriptSegment.canDisplaySeconds(ordered), isTrue);
  });
}
