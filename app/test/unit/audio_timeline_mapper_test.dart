import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/audio/audio_timeline_mapper.dart';

void main() {
  // Vectors mirrored from backend tests/unit/test_conversation_playback_artifact.py:
  //   started_at = 990.0; part A: chunk ts 1000.0, 10.0s; part B: chunk ts 1200.0, 5.0s
  //   spans: A {wall 10.0, artifact 0.0, len 10.0}, B {wall 210.0, artifact 10.0, len 5.0}
  final spans = [
    const ConversationAudioSpan(fileId: 'A', wallOffset: 10.0, artifactOffset: 0.0, len: 10.0),
    const ConversationAudioSpan(fileId: 'B', wallOffset: 210.0, artifactOffset: 10.0, len: 5.0),
  ];
  final mapper = AudioTimelineMapper(spans);

  group('AudioTimelineMapper', () {
    test('durations match the backend stamp', () {
      expect(mapper.capturedDuration, 15.0);
      expect(mapper.wallDuration, 215.0);
    });

    test('wallToArtifact inside spans is exact arithmetic', () {
      expect(mapper.wallToArtifact(10.0), 0.0);
      expect(mapper.wallToArtifact(15.0), 5.0);
      expect(mapper.wallToArtifact(20.0), 10.0); // end of A == start of B in artifact time
      expect(mapper.wallToArtifact(212.5), 12.5);
      expect(mapper.wallToArtifact(215.0), 15.0);
    });

    test('wallToArtifact in a collapsed gap snaps to the next span', () {
      expect(mapper.wallToArtifact(100.0), 10.0);
      expect(mapper.wallToArtifact(209.9), 10.0);
    });

    test('wallToArtifact clamps outside the timeline', () {
      expect(mapper.wallToArtifact(0.0), 0.0);
      expect(mapper.wallToArtifact(-5.0), 0.0);
      expect(mapper.wallToArtifact(999.0), 15.0);
    });

    test('artifactToWall round-trips positions inside spans', () {
      for (final wall in [10.0, 15.0, 19.9, 210.0, 212.5, 215.0]) {
        expect(mapper.artifactToWall(mapper.wallToArtifact(wall)), closeTo(wall, 1e-9));
      }
    });

    test('artifactToWall maps the artifact seam to the second span start', () {
      expect(mapper.artifactToWall(10.0), 210.0);
      expect(mapper.artifactToWall(12.5), 212.5);
    });

    test('gapRangesWall exposes the collapsed gap for scrubber shading', () {
      expect(mapper.gapRangesWall, [(20.0, 210.0)]);
    });

    test('unsorted span input is sorted on construction', () {
      final shuffled = AudioTimelineMapper([spans[1], spans[0]]);
      expect(shuffled.wallToArtifact(212.5), 12.5);
      expect(shuffled.capturedDuration, 15.0);
    });

    test('empty spans are inert', () {
      final empty = AudioTimelineMapper(const []);
      expect(empty.isEmpty, isTrue);
      expect(empty.capturedDuration, 0);
      expect(empty.wallDuration, 0);
      expect(empty.wallToArtifact(5.0), 0);
      expect(empty.artifactToWall(5.0), 0);
      expect(empty.gapRangesWall, isEmpty);
    });

    test('fromJson parses the backend span shape', () {
      final span = ConversationAudioSpan.fromJson(const {
        'file_id': 'A',
        'wall_offset': 10.0,
        'artifact_offset': 0,
        'len': 10.0,
      });
      expect(span.fileId, 'A');
      expect(span.wallOffset, 10.0);
      expect(span.artifactOffset, 0.0);
      expect(span.len, 10.0);
    });
  });
}
